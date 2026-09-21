"""Creating, listing and reading videos."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Row, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.topic import Topic
from app.models.user import User
from app.models.video import (
    CATEGORIES,
    LINK_KINDS,
    VIDEO_TYPES,
    VISIBILITIES,
    UploadEvent,
    Video,
    VideoLink,
    VideoSnippet,
    VideoViewer,
)

PAGE_SIZE = 24


class VideoError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.field = field


def validate_metadata(video_type: str, category: str, visibility: str) -> None:
    if video_type not in VIDEO_TYPES:
        raise VideoError(f"Type must be one of: {', '.join(VIDEO_TYPES)}", field="type")
    if category not in CATEGORIES:
        raise VideoError(f"Unknown category '{category}'", field="category")
    if visibility not in VISIBILITIES:
        raise VideoError(f"Unknown visibility '{visibility}'", field="visibility")


def raw_object_name(settings: Settings, owner_id: uuid.UUID, video_id: uuid.UUID, filename: str) -> str:
    """raw/users/{user_id}/videos/{video_id}/source.<ext> — one folder per user."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    extension = "".join(c for c in extension if c.isalnum())[:5] or "mp4"
    return settings.raw_object("users", str(owner_id), "videos", str(video_id), f"source.{extension}")


async def save_resources(session: AsyncSession, video: Video, links: list, snippets: list) -> None:
    """Attach the optional links and code snippets from the upload form."""
    now = datetime.now(UTC)
    for link in links:
        kind = link.kind if link.kind in LINK_KINDS else "other"
        session.add(
            VideoLink(video_id=video.id, kind=kind, url=link.url, label=link.label or None, created_at=now)
        )
    for order, snippet in enumerate(snippets):
        session.add(
            VideoSnippet(
                video_id=video.id,
                title=snippet.title or None,
                language=snippet.language,
                code=snippet.code,
                sort_order=order,
                created_at=now,
            )
        )


async def resources_for(session: AsyncSession, video_id: uuid.UUID) -> dict:
    links = (
        await session.scalars(
            select(VideoLink).where(VideoLink.video_id == video_id).order_by(VideoLink.created_at)
        )
    ).all()
    snippets = (
        await session.scalars(
            select(VideoSnippet).where(VideoSnippet.video_id == video_id).order_by(VideoSnippet.sort_order)
        )
    ).all()
    return {"links": list(links), "snippets": list(snippets)}


async def topic_by_slug(session: AsyncSession, slug: str | None) -> Topic | None:
    if not slug:
        return None
    topic = await session.scalar(select(Topic).where(Topic.slug == slug, Topic.is_active))
    if topic is None:
        raise VideoError(f"Unknown topic '{slug}'", field="topic_slug")
    return topic


def record_event(
    session: AsyncSession, video: Video, user_id: uuid.UUID | None, event: str, **metadata
) -> None:
    """Append to the upload audit trail (who did what to this video, and when)."""
    session.add(
        UploadEvent(
            video_id=video.id,
            user_id=user_id,
            event=event,
            event_metadata=metadata,
            created_at=datetime.now(UTC),
        )
    )


# ------------------------------------------------------------------ queries
def _row_to_out(row: Row) -> dict:
    video, display_name, handle, topic_slug, topic_name = row
    return {
        **{c.name: getattr(video, c.name) for c in video.__table__.columns if hasattr(video, c.name)},
        "has_thumbnail": bool(video.thumbnail_path),
        "owner_display_name": display_name,
        "owner_handle": handle,
        "topic_slug": topic_slug,
        "topic_name": topic_name,
    }


def _base_query():
    return (
        select(Video, User.display_name, User.handle, Topic.slug, Topic.name)
        .join(User, User.id == Video.owner_id)
        .outerjoin(Topic, Topic.id == Video.primary_topic_id)
        .where(Video.deleted_at.is_(None))
    )


def _allowed_ids(viewer: User):
    return select(VideoViewer.video_id).where(VideoViewer.user_id == viewer.id).scalar_subquery()


def visible_clause(viewer: User | None):
    """Which videos this person may see in a list: everyone's internal ones, their own,
    and the restricted ones they were added to. Unlisted videos are link-only."""
    public = Video.visibility == "internal"
    if viewer is None:
        return public
    shared_with_me = (Video.visibility == "restricted") & Video.id.in_(_allowed_ids(viewer))
    return public | (Video.owner_id == viewer.id) | shared_with_me


async def may_watch(session: AsyncSession, video: Video, viewer: User | None) -> bool:
    """Whether this person may open the watch page for a single video."""
    if viewer is not None and (viewer.id == video.owner_id or viewer.role == "admin"):
        return True
    if video.visibility in ("internal", "unlisted"):
        return True
    if video.visibility == "restricted" and viewer is not None:
        return (await session.get(VideoViewer, {"video_id": video.id, "user_id": viewer.id})) is not None
    return False  # private


async def list_feed(
    session: AsyncSession,
    *,
    video_type: str | None = None,
    topic_slug: str | None = None,
    owner_id: uuid.UUID | None = None,
    viewer: User | None = None,
    limit: int = PAGE_SIZE,
) -> list[dict]:
    """Newest first. Private videos are only visible to their owner."""
    query = _base_query().where(Video.status == "READY", visible_clause(viewer))
    if video_type:
        query = query.where(Video.type == video_type)
    if topic_slug:
        query = query.where(Topic.slug == topic_slug)
    if owner_id:
        query = query.where(Video.owner_id == owner_id)

    rows = await session.execute(query.order_by(Video.published_at.desc().nullslast()).limit(limit))
    return [_row_to_out(row) for row in rows]


async def get_video(session: AsyncSession, video_id: uuid.UUID, viewer: User | None) -> dict:
    row = (await session.execute(_base_query().where(Video.id == video_id))).one_or_none()
    if row is None:
        raise VideoError("Video not found", status_code=404)
    video: Video = row[0]
    if not await may_watch(session, video, viewer):
        raise VideoError("Video not found", status_code=404)
    if video.status != "READY" and (viewer is None or viewer.id != video.owner_id):
        raise VideoError("This video is still processing", status_code=409)
    return {**_row_to_out(row), **await resources_for(session, video.id)}


# ------------------------------------------------------ channel management
async def get_owned(session: AsyncSession, video_id: uuid.UUID, user: User) -> Video:
    video = await session.get(Video, video_id)
    if video is None or video.deleted_at is not None:
        raise VideoError("Video not found", status_code=404)
    if video.owner_id != user.id and user.role != "admin":
        raise VideoError("This isn't your video", status_code=403)
    return video


async def viewers_for(session: AsyncSession, video_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    """The allow-list behind visibility='restricted', per video."""
    if not video_ids:
        return {}
    rows = await session.execute(
        select(VideoViewer.video_id, User.id, User.display_name, User.handle)
        .join(User, User.id == VideoViewer.user_id)
        .where(VideoViewer.video_id.in_(video_ids))
        .order_by(User.display_name)
    )
    people: dict[uuid.UUID, list[dict]] = {video_id: [] for video_id in video_ids}
    for video_id, user_id, display_name, handle in rows:
        people[video_id].append({"id": user_id, "display_name": display_name, "handle": handle})
    return people


async def set_viewers(
    session: AsyncSession, video: Video, user_ids: list[uuid.UUID], added_by: User
) -> list[dict]:
    """Replace the allow-list. The owner is always allowed, so they never appear in it."""
    wanted = {uid for uid in user_ids if uid != video.owner_id}
    if wanted:
        found = set(
            (
                await session.scalars(
                    select(User.id).where(User.id.in_(wanted), User.is_active, User.deleted_at.is_(None))
                )
            ).all()
        )
        if missing := wanted - found:
            raise VideoError(f"{len(missing)} of those people no longer have an account")
        wanted = found

    current = set(
        (await session.scalars(select(VideoViewer.user_id).where(VideoViewer.video_id == video.id))).all()
    )
    for user_id in current - wanted:
        await session.execute(
            delete(VideoViewer).where(VideoViewer.video_id == video.id, VideoViewer.user_id == user_id)
        )
    now = datetime.now(UTC)
    for user_id in wanted - current:
        session.add(VideoViewer(video_id=video.id, user_id=user_id, added_by=added_by.id, created_at=now))
    await session.flush()
    return (await viewers_for(session, [video.id]))[video.id]


async def replace_resources(session: AsyncSession, video: Video, links, snippets) -> None:
    """Swap the links and snippets for the ones the owner just saved."""
    if links is not None:
        await session.execute(delete(VideoLink).where(VideoLink.video_id == video.id))
    if snippets is not None:
        await session.execute(delete(VideoSnippet).where(VideoSnippet.video_id == video.id))
    await save_resources(session, video, links or [], snippets or [])


async def apply_patch(session: AsyncSession, video: Video, user: User, patch) -> list[str]:
    """Apply the owner's edits. Returns the names of the fields that actually changed."""
    changed: list[str] = []

    if patch.title is not None and patch.title.strip() != video.title:
        video.title = patch.title.strip()
        changed.append("title")
    if patch.description is not None:
        description = patch.description.strip() or None
        if description != video.description:
            video.description = description
            changed.append("description")
    if patch.category is not None and patch.category != video.category:
        if patch.category not in CATEGORIES:
            raise VideoError(f"Unknown category '{patch.category}'", field="category")
        video.category = patch.category
        changed.append("category")
    if patch.topic_slug is not None:
        topic = await topic_by_slug(session, patch.topic_slug or None)
        topic_id = topic.id if topic else None
        if topic_id != video.primary_topic_id:
            video.primary_topic_id = topic_id
            changed.append("topic")
    if patch.visibility is not None and patch.visibility != video.visibility:
        if patch.visibility not in VISIBILITIES:
            raise VideoError(f"Unknown visibility '{patch.visibility}'", field="visibility")
        video.visibility = patch.visibility
        changed.append("visibility")
    if patch.comments_enabled is not None and patch.comments_enabled != video.comments_enabled:
        video.comments_enabled = patch.comments_enabled
        changed.append("comments")
    if patch.viewer_ids is not None:
        before = set(
            (await session.scalars(select(VideoViewer.user_id).where(VideoViewer.video_id == video.id))).all()
        )
        await set_viewers(session, video, patch.viewer_ids, user)
        if before != {uid for uid in patch.viewer_ids if uid != video.owner_id}:
            changed.append("people")
    if patch.links is not None or patch.snippets is not None:
        await replace_resources(session, video, patch.links, patch.snippets)
        changed.append("resources")

    if changed:
        record_event(session, video, user.id, "edited", fields=changed)
    if "visibility" in changed:
        record_event(session, video, user.id, "visibility_changed", visibility=video.visibility)
    if "comments" in changed:
        record_event(session, video, user.id, "comments_changed", enabled=video.comments_enabled)
    return changed


async def soft_delete(session: AsyncSession, video: Video, user: User) -> list[str]:
    """Take the video down. The row stays for the audit trail; the files are removed by
    the caller, which owns the storage adapter."""
    video.deleted_at = datetime.now(UTC)
    record_event(session, video, user.id, "deleted")
    return [path for path in (video.raw_gcs_path, video.thumbnail_path) if path]


async def channel_for(session: AsyncSession, handle: str, viewer: User | None) -> dict:
    """A user's channel: their profile and their videos. The owner sees everything,
    including drafts, failed uploads and hidden videos."""
    owner = await session.scalar(
        select(User).where(User.handle == handle.lstrip("@").lower(), User.deleted_at.is_(None))
    )
    if owner is None:
        raise VideoError("Channel not found", status_code=404)
    is_owner = viewer is not None and viewer.id == owner.id

    query = _base_query().where(Video.owner_id == owner.id)
    if is_owner:
        query = query.order_by(Video.created_at.desc())
    else:
        # other people see published videos only, and never the link-only ones
        query = query.where(
            Video.status == "READY", Video.visibility != "unlisted", visible_clause(viewer)
        ).order_by(Video.published_at.desc().nullslast())

    rows = (await session.execute(query)).all()
    videos = [_row_to_out(row) for row in rows]
    if is_owner:
        people = await viewers_for(session, [item["id"] for item in videos])
        for item in videos:
            item["allowed_viewers"] = people.get(item["id"], [])

    return {
        "id": owner.id,
        "handle": owner.handle,
        "display_name": owner.display_name,
        "bio": owner.bio,
        "avatar_url": owner.avatar_url,
        "joined_at": owner.created_at,
        "is_me": is_owner,
        "video_count": len(videos),
        "total_views": sum(item["view_count"] for item in videos),
        "videos": videos,
    }
