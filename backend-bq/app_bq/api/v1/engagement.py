"""Likes, comments, sharing and view counts: the BigQuery twin of app/api/v1/engagement.py."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import Settings, get_settings
from app.schemas.engagement import (
    CommentIn,
    CommentOut,
    ReactionIn,
    ReactionOut,
    SharedVideo,
    ShareIn,
    UserSuggestion,
)
from app_bq.api.deps import current_user, current_user_optional
from app_bq.core.bq import BigQueryDB, Row, get_db
from app_bq.services import engagement
from app_bq.services import video as video_service

router = APIRouter(tags=["engagement"])


def _fail(error: video_service.VideoError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail={"message": error.message})


async def _visible_video(db: BigQueryDB, video_id: uuid.UUID, viewer: Row | None) -> Row:
    """The video, if this person may see it; otherwise the same 404 the watch page gives."""
    try:
        return Row(await video_service.get_video(db, video_id, viewer, with_resources=False))
    except video_service.VideoError as exc:
        raise _fail(exc) from exc


def _comment_out(comment: Row, user: Row, *, is_uploader: bool, like_count: int = 0) -> CommentOut:
    return CommentOut.model_validate(
        {
            "id": comment.id,
            "video_id": comment.video_id,
            "parent_id": comment.parent_id,
            "body": comment.body,
            "like_count": like_count,
            "is_pinned": comment.is_pinned,
            "created_at": comment.created_at,
            "edited_at": comment.get("edited_at"),
            "author_id": user.id,
            "author_name": user.display_name,
            "author_handle": user.handle,
            "liked_by_me": False,
            "is_mine": True,
            "is_uploader": is_uploader,
            "replies": [],
        }
    )


# ------------------------------------------------------------------ reactions
@router.put("/videos/{video_id}/reaction", response_model=ReactionOut)
async def set_reaction(
    video_id: uuid.UUID,
    data: ReactionIn,
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
) -> ReactionOut:
    """Like (1), dislike (-1) or clear (0). Pressing the same button again clears it."""
    video = await _visible_video(db, video_id, user)
    likes, dislikes, mine = await engagement.set_reaction(db, video, user, data.value)
    return ReactionOut(like_count=likes, dislike_count=dislikes, my_reaction=mine)


@router.get("/videos/{video_id}/reaction", response_model=ReactionOut)
async def get_reaction(
    video_id: uuid.UUID,
    user: Row | None = Depends(current_user_optional),
    db: BigQueryDB = Depends(get_db),
) -> ReactionOut:
    await _visible_video(db, video_id, user)
    likes, dislikes, mine = await engagement.counts_for(db, video_id, user)
    return ReactionOut(like_count=likes, dislike_count=dislikes, my_reaction=mine)


# ------------------------------------------------------------------ comments
@router.get("/videos/{video_id}/comments", response_model=list[CommentOut])
async def list_comments(
    video_id: uuid.UUID,
    sort: str = Query(default="top", pattern="^(top|new)$"),
    user: Row | None = Depends(current_user_optional),
    db: BigQueryDB = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[CommentOut]:
    await _visible_video(db, video_id, user)
    items = await engagement.list_comments(db, video_id, user, sort, settings.comment_edit_window_seconds)
    return [CommentOut.model_validate(item) for item in items]


@router.post("/videos/{video_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(
    video_id: uuid.UUID,
    data: CommentIn,
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
) -> CommentOut:
    video = await _visible_video(db, video_id, user)
    try:
        comment = await engagement.add_comment(db, video, user, data.body, data.parent_id)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    return _comment_out(comment, user, is_uploader=video.owner_id == user.id)


@router.patch("/comments/{comment_id}", response_model=CommentOut)
async def edit_comment(
    comment_id: uuid.UUID,
    data: CommentIn,
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CommentOut:
    """Fix a typo shortly after posting; see COMMENT_EDIT_WINDOW_SECONDS."""
    try:
        comment = await engagement.edit_comment(
            db, comment_id, user, data.body, settings.comment_edit_window_seconds
        )
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    return _comment_out(comment, user, is_uploader=False, like_count=comment.like_count or 0)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: uuid.UUID,
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
) -> None:
    """Authors delete their own; the uploader can remove any comment on their video."""
    try:
        await engagement.delete_comment(db, comment_id, user)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc


@router.put("/comments/{comment_id}/reaction")
async def like_comment(
    comment_id: uuid.UUID,
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
) -> dict:
    try:
        like_count, liked = await engagement.toggle_comment_like(db, comment_id, user)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    return {"like_count": like_count, "liked_by_me": liked}


# ------------------------------------------------------------------ sharing
@router.get("/users/search", response_model=list[UserSuggestion])
async def search_users(
    q: str = Query(min_length=1, max_length=80),
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
) -> list[UserSuggestion]:
    """Find colleagues to share a video with."""
    return [UserSuggestion(**person) for person in await engagement.search_people(db, q, user)]


@router.post("/videos/{video_id}/share", status_code=status.HTTP_201_CREATED)
async def share_video(
    video_id: uuid.UUID,
    data: ShareIn,
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
) -> dict:
    """Share inside KnowHub: recipients get a notification and a "Shared with me" entry."""
    video = await _visible_video(db, video_id, user)
    try:
        sent = await engagement.share_video(db, video, user, data.to_user_ids, data.message, data.at_seconds)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    return {"shared_with": sent}


@router.get("/shared-with-me", response_model=list[SharedVideo])
async def shared_with_me(
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
) -> list[SharedVideo]:
    return [SharedVideo(**item) for item in await engagement.shared_with_me(db, user)]


# ------------------------------------------------------------------ views
@router.post("/videos/{video_id}/view")
async def count_view(
    video_id: uuid.UUID,
    user: Row | None = Depends(current_user_optional),
    db: BigQueryDB = Depends(get_db),
) -> dict:
    """Called by the player once playback starts. Open to anonymous viewers."""
    await _visible_video(db, video_id, user)
    return {"view_count": await engagement.count_view(db, video_id, user)}
