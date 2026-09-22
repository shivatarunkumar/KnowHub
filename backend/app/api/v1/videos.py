"""Upload, browse, watch.

The file is uploaded through the API and stored in GCS under
raw/users/{user_id}/videos/{video_id}/source.*, and played back through
GET /videos/{id}/stream, which supports range requests so the player can seek.

Later phases replace this with: a signed URL so the browser uploads straight to GCS,
a worker that transcodes to HLS, and playback from the CDN.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import StorageService, get_storage
from app.api.deps import current_user, current_user_optional
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.models.user import User
from app.models.video import Video
from app.schemas.video import LinkIn, SnippetIn, VideoOut, VideoPage, VideoUpdate
from app.services import video as video_service

router = APIRouter(tags=["videos"])
log = logging.getLogger("knowhub.video")

ALLOWED_MIME_PREFIX = "video/"
UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024  # 8 MB: a multiple of 256 KiB, as GCS requires


class UploadStart(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    content_type: str
    size: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    type: str = "video"
    category: str
    topic_slug: str = ""
    team_slug: str = ""
    visibility: str = "internal"
    # measured in the browser before upload
    duration_sec: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    # optional extras so viewers can copy instead of transcribing from the video
    links: list[LinkIn] = []
    snippets: list[SnippetIn] = []


class UploadSession(BaseModel):
    video_id: uuid.UUID
    upload_url: str
    chunk_size: int


def _fail(error: video_service.VideoError) -> HTTPException:
    detail: dict = {"message": error.message}
    if error.field:
        detail["field"] = error.field
    return HTTPException(status_code=error.status_code, detail=detail)


@router.post("/videos/uploads/start", response_model=UploadSession, status_code=status.HTTP_201_CREATED)
async def start_upload(
    data: UploadStart,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    storage: StorageService = Depends(get_storage),
) -> UploadSession:
    """Create the video record and hand the browser a URL to upload the file directly to
    storage, in chunks. Used for every upload; see POST /videos/{id}/complete."""
    try:
        video_service.validate_metadata(data.type, data.category, data.visibility)
        topic = await video_service.topic_by_slug(session, data.topic_slug or None)
        team = await video_service.team_by_slug(session, data.team_slug or None)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc

    if not data.content_type.startswith(ALLOWED_MIME_PREFIX):
        raise _fail(
            video_service.VideoError(
                f"That file is {data.content_type}; please choose a video file", field="file"
            )
        )
    if data.size > settings.max_video_bytes:
        limit_gb = settings.max_video_bytes / 1024**3
        raise _fail(
            video_service.VideoError(f"That file is larger than the {limit_gb:.0f} GB limit", field="file")
        )

    video = Video(
        id=uuid.uuid4(),
        owner_id=user.id,
        type=data.type,
        title=data.title.strip(),
        description=data.description.strip() or None,
        category=data.category,
        primary_topic_id=topic.id if topic else None,
        team_id=team.id if team else None,
        visibility=data.visibility,
        status="UPLOADING",
        original_filename=data.filename,
        mime_type=data.content_type,
        duration_sec=data.duration_sec,
        width=data.width,
        height=data.height,
    )
    session.add(video)
    await session.flush()

    object_name = video_service.raw_object_name(settings, user.id, video.id, data.filename)
    origin = request.headers.get("origin") or settings.web_base_url
    try:
        upload_url = await asyncio.to_thread(
            storage.resumable_session, object_name, data.content_type, data.size, origin
        )
    except Exception as exc:
        log.exception("could not open a resumable session for %s (origin %s)", object_name, origin)
        raise HTTPException(
            status_code=502, detail={"message": "Could not start the upload. Please try again."}
        ) from exc

    log.info(
        "upload started: video=%s %s %.1f MB -> gs://%s/%s",
        video.id,
        data.content_type,
        data.size / 1024**2,
        settings.gcs_bucket,
        object_name,
    )
    video.raw_gcs_path = object_name
    if team is not None and user.team_id is None:
        # first upload tells us which team this person is in; the form defaults to it next time
        user.team_id = team.id
    await video_service.save_resources(session, video, data.links, data.snippets)
    video_service.record_event(
        session,
        video,
        user.id,
        "initiated",
        filename=data.filename,
        bytes=data.size,
        links=len(data.links),
        snippets=len(data.snippets),
    )
    await session.commit()
    return UploadSession(video_id=video.id, upload_url=upload_url, chunk_size=UPLOAD_CHUNK_BYTES)


@router.post("/videos/{video_id}/complete", response_model=VideoOut)
async def complete_upload(
    video_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage),
) -> VideoOut:
    """Called once the browser has finished uploading: check the file really is in
    storage, then publish the video."""
    try:
        video = await video_service.get_owned(session, video_id, user)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc

    stat = await asyncio.to_thread(storage.stat, video.raw_gcs_path or "")
    if stat is None:
        log.error(
            "upload finished but %s is not in the bucket: the browser's PUTs did not complete",
            video.raw_gcs_path,
        )
        video.status = "FAILED"
        video.processing_error = "file missing from storage after upload"
        video_service.record_event(session, video, user.id, "failed", reason="missing object")
        await session.commit()
        raise HTTPException(
            status_code=409, detail={"message": "The upload didn't finish. Please try again."}
        )

    size, _ = stat
    video.size_bytes = size
    video.status = "READY"
    video.published_at = video.published_at or datetime.now(UTC)
    video_service.record_event(session, video, user.id, "uploaded", bytes=size)
    video_service.record_event(session, video, user.id, "published")
    await session.commit()
    log.info("upload complete: video=%s %.1f MB, now READY", video.id, size / 1024**2)

    data = await video_service.get_video(session, video.id, user)
    return VideoOut.model_validate(data)


@router.post("/videos/upload", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: Annotated[UploadFile, File(description="the video file")],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    category: Annotated[str, Form()],
    description: Annotated[str, Form(max_length=20000)] = "",
    video_type: Annotated[str, Form(alias="type")] = "video",
    topic_slug: Annotated[str, Form()] = "",
    team_slug: Annotated[str, Form()] = "",
    visibility: Annotated[str, Form()] = "internal",
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    storage: StorageService = Depends(get_storage),
) -> VideoOut:
    """Upload a small video in one request (used by tests and scripts). Browsers use
    /videos/uploads/start instead, which streams straight to storage."""
    try:
        video_service.validate_metadata(video_type, category, visibility)
        topic = await video_service.topic_by_slug(session, topic_slug or None)
        team = await video_service.team_by_slug(session, team_slug or None)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc

    content_type = file.content_type or "application/octet-stream"
    if not content_type.startswith(ALLOWED_MIME_PREFIX):
        raise _fail(
            video_service.VideoError(f"That file is {content_type}; please choose a video file", field="file")
        )

    video = Video(
        id=uuid.uuid4(),
        owner_id=user.id,
        type=video_type,
        title=title.strip(),
        description=description.strip() or None,
        category=category,
        primary_topic_id=topic.id if topic else None,
        team_id=team.id if team else None,
        visibility=visibility,
        status="UPLOADING",
        original_filename=file.filename,
        mime_type=content_type,
    )
    session.add(video)
    await session.flush()
    video_service.record_event(session, video, user.id, "initiated", filename=file.filename)
    await session.commit()

    object_name = video_service.raw_object_name(settings, user.id, video.id, file.filename or "video.mp4")
    try:
        size = await asyncio.to_thread(storage.upload, object_name, file.file, content_type)
    except Exception as exc:
        video.status = "FAILED"
        video.processing_error = f"{exc.__class__.__name__}: {exc}"[:500]
        video_service.record_event(session, video, user.id, "failed", error=str(exc)[:500])
        await session.commit()
        raise HTTPException(
            status_code=502, detail={"message": "Upload to storage failed. Please try again."}
        ) from exc

    if size > settings.max_video_bytes:
        await asyncio.to_thread(storage.delete, object_name)
        video.status = "FAILED"
        await session.commit()
        limit_gb = settings.max_video_bytes / 1024**3
        raise _fail(
            video_service.VideoError(f"That file is larger than the {limit_gb:.0f} GB limit", field="file")
        )

    # No transcoding yet (Phase 2b), so the original file is what gets played.
    video.raw_gcs_path = object_name
    video.size_bytes = size
    video.status = "READY"
    video.published_at = datetime.now(UTC)
    video_service.record_event(session, video, user.id, "uploaded", object=object_name, bytes=size)
    video_service.record_event(session, video, user.id, "published")
    await session.commit()

    return VideoOut.model_validate(
        {
            **{c.name: getattr(video, c.name) for c in video.__table__.columns},
            "owner_display_name": user.display_name,
            "owner_handle": user.handle,
            "topic_slug": topic.slug if topic else None,
            "topic_name": topic.name if topic else None,
            "team_slug": team.slug if team else None,
            "team_name": team.name if team else None,
        }
    )


MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024


@router.post("/videos/{video_id}/thumbnail", status_code=status.HTTP_204_NO_CONTENT)
async def upload_thumbnail(
    video_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="JPEG or PNG still from the video")],
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    storage: StorageService = Depends(get_storage),
) -> None:
    """Store the poster frame the browser captured from the video."""
    try:
        video = await video_service.get_owned(session, video_id, user)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc

    content_type = file.content_type or ""
    if content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise _fail(video_service.VideoError("Thumbnails must be JPEG, PNG or WebP", field="file"))

    object_name = settings.media_object("videos", str(video.id), "thumbs", "default.jpg")
    size = await asyncio.to_thread(storage.upload, object_name, file.file, content_type)
    if size > MAX_THUMBNAIL_BYTES:
        await asyncio.to_thread(storage.delete, object_name)
        raise _fail(video_service.VideoError("That thumbnail is too large", field="file"))

    video.thumbnail_path = object_name
    await session.commit()


@router.get("/videos/{video_id}/thumbnail")
async def get_thumbnail(
    video_id: uuid.UUID,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage),
):
    """Serve the poster frame; 404 when the video has none, so the UI draws its own cover."""
    try:
        data = await video_service.get_video(session, video_id, user)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc

    object_name = data.get("thumbnail_path")
    if not object_name:
        raise HTTPException(status_code=404, detail={"message": "No thumbnail"})
    stat = await asyncio.to_thread(storage.stat, object_name)
    if stat is None:
        raise HTTPException(status_code=404, detail={"message": "No thumbnail"})
    size, content_type = stat

    def chunks():
        yield from storage.download(object_name, 0, size - 1)

    return StreamingResponse(
        chunks(),
        media_type=content_type,
        headers={"Content-Length": str(size), "Cache-Control": "public, max-age=86400"},
    )


@router.patch("/videos/{video_id}", response_model=VideoOut)
async def update_video(
    video_id: uuid.UUID,
    data: VideoUpdate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> VideoOut:
    """Edit a video from your channel: wording, topic, who can see it, comments on or off.
    Only the fields you send change."""
    try:
        video = await video_service.get_owned(session, video_id, user)
        await video_service.apply_patch(session, video, user, data)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    await session.commit()
    return VideoOut.model_validate(await video_service.get_video(session, video_id, user))


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage),
) -> None:
    """Take a video down for good. The row stays so the upload audit trail is intact,
    but it disappears from every feed and its files are removed from storage."""
    try:
        video = await video_service.get_owned(session, video_id, user)
        objects = await video_service.soft_delete(session, video, user)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    await session.commit()

    log.info("video %s deleted by %s, removing %d object(s)", video_id, user.handle, len(objects))
    for object_name in objects:
        # the video is already gone from the UI; a leftover object isn't worth an error
        with contextlib.suppress(Exception):
            await asyncio.to_thread(storage.delete, object_name)


@router.get("/videos/feed", response_model=VideoPage)
async def feed(
    video_type: str | None = Query(default=None, alias="type"),
    topic: Annotated[list[str] | None, Query(description="repeat for several: ?topic=a&topic=b")] = None,
    team: str | None = None,
    limit: int = 24,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> VideoPage:
    """Newest videos, optionally filtered by type, topic(s) or team. Open to anyone.

    Several topics mean "any of these"; a topic and a team together mean both."""
    items = await video_service.list_feed(
        session,
        video_type=video_type,
        topic_slugs=topic,
        team_slug=team,
        viewer=user,
        limit=min(limit, 100),
    )
    return VideoPage(items=[VideoOut.model_validate(item) for item in items])


@router.get("/videos/{video_id}", response_model=VideoOut)
async def get_video(
    video_id: uuid.UUID,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> VideoOut:
    try:
        return VideoOut.model_validate(await video_service.get_video(session, video_id, user))
    except video_service.VideoError as exc:
        raise _fail(exc) from exc


@router.get("/videos/{video_id}/stream")
async def stream_video(
    video_id: uuid.UUID,
    request: Request,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage),
):
    """Serve the video file, honouring Range requests so the player can seek."""
    try:
        data = await video_service.get_video(session, video_id, user)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc

    object_name = data.get("raw_gcs_path")
    if not object_name:
        raise HTTPException(status_code=404, detail={"message": "No file for this video"})

    stat = await asyncio.to_thread(storage.stat, object_name)
    if stat is None:
        raise HTTPException(status_code=404, detail={"message": "File missing from storage"})
    size, content_type = stat

    start, end = 0, size - 1
    status_code = status.HTTP_200_OK
    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        raw_start, _, raw_end = range_header.removeprefix("bytes=").partition("-")
        try:
            start = int(raw_start) if raw_start else 0
            end = int(raw_end) if raw_end else size - 1
        except ValueError:
            start, end = 0, size - 1
        if start >= size:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{size}"},
            )
        end = min(end, size - 1)
        status_code = status.HTTP_206_PARTIAL_CONTENT

    headers = {
        "Content-Length": str(end - start + 1),
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
    }
    if status_code == status.HTTP_206_PARTIAL_CONTENT:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    def chunks():
        yield from storage.download(object_name, start, end)

    return StreamingResponse(chunks(), status_code=status_code, media_type=content_type, headers=headers)
