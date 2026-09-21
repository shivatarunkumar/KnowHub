"""Likes, comments, sharing and view counts."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, current_user_optional
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.models.user import User
from app.schemas.engagement import (
    CommentIn,
    CommentOut,
    ReactionIn,
    ReactionOut,
    SharedVideo,
    ShareIn,
    UserSuggestion,
)
from app.services import engagement
from app.services import video as video_service

router = APIRouter(tags=["engagement"])


def _fail(error: video_service.VideoError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail={"message": error.message})


async def _visible_video(session: AsyncSession, video_id: uuid.UUID, viewer: User | None):
    try:
        await video_service.get_video(session, video_id, viewer)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    from app.models.video import Video

    return await session.get(Video, video_id)


# ------------------------------------------------------------------ reactions
@router.put("/videos/{video_id}/reaction", response_model=ReactionOut)
async def set_reaction(
    video_id: uuid.UUID,
    data: ReactionIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ReactionOut:
    """Like (1), dislike (-1) or clear (0). Pressing the same button again clears it."""
    video = await _visible_video(session, video_id, user)
    likes, dislikes, mine = await engagement.set_reaction(session, video, user, data.value)
    return ReactionOut(like_count=likes, dislike_count=dislikes, my_reaction=mine)


@router.get("/videos/{video_id}/reaction", response_model=ReactionOut)
async def get_reaction(
    video_id: uuid.UUID,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> ReactionOut:
    await _visible_video(session, video_id, user)
    likes, dislikes = await engagement.counts_for(session, video_id)
    return ReactionOut(
        like_count=likes,
        dislike_count=dislikes,
        my_reaction=await engagement.my_reaction(session, video_id, user),
    )


# ------------------------------------------------------------------ comments
@router.get("/videos/{video_id}/comments", response_model=list[CommentOut])
async def list_comments(
    video_id: uuid.UUID,
    sort: str = Query(default="top", pattern="^(top|new)$"),
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[CommentOut]:
    await _visible_video(session, video_id, user)
    items = await engagement.list_comments(
        session, video_id, user, sort, settings.comment_edit_window_seconds
    )
    return [CommentOut.model_validate(item) for item in items]


@router.post("/videos/{video_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(
    video_id: uuid.UUID,
    data: CommentIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CommentOut:
    video = await _visible_video(session, video_id, user)
    try:
        comment = await engagement.add_comment(session, video, user, data.body, data.parent_id)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    return CommentOut.model_validate(
        {
            "id": comment.id,
            "video_id": comment.video_id,
            "parent_id": comment.parent_id,
            "body": comment.body,
            "like_count": 0,
            "is_pinned": False,
            "created_at": comment.created_at,
            "edited_at": None,
            "author_id": user.id,
            "author_name": user.display_name,
            "author_handle": user.handle,
            "liked_by_me": False,
            "is_mine": True,
            "is_uploader": video.owner_id == user.id,
            "replies": [],
        }
    )


@router.patch("/comments/{comment_id}", response_model=CommentOut)
async def edit_comment(
    comment_id: uuid.UUID,
    data: CommentIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CommentOut:
    """Fix a typo shortly after posting; see COMMENT_EDIT_WINDOW_SECONDS."""
    try:
        comment = await engagement.edit_comment(
            session, comment_id, user, data.body, settings.comment_edit_window_seconds
        )
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    return CommentOut.model_validate(
        {
            "id": comment.id,
            "video_id": comment.video_id,
            "parent_id": comment.parent_id,
            "body": comment.body,
            "like_count": comment.like_count,
            "is_pinned": comment.is_pinned,
            "created_at": comment.created_at,
            "edited_at": comment.edited_at,
            "author_id": user.id,
            "author_name": user.display_name,
            "author_handle": user.handle,
            "liked_by_me": False,
            "is_mine": True,
            "is_uploader": False,
            "replies": [],
        }
    )


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Authors delete their own; the uploader can remove any comment on their video."""
    try:
        await engagement.delete_comment(session, comment_id, user)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc


@router.put("/comments/{comment_id}/reaction")
async def like_comment(
    comment_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        like_count, liked = await engagement.toggle_comment_like(session, comment_id, user)
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    return {"like_count": like_count, "liked_by_me": liked}


# ------------------------------------------------------------------ sharing
@router.get("/users/search", response_model=list[UserSuggestion])
async def search_users(
    q: str = Query(min_length=1, max_length=80),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[UserSuggestion]:
    """Find colleagues to share a video with."""
    people = await engagement.search_people(session, q, user)
    return [UserSuggestion(**person) for person in people]


@router.post("/videos/{video_id}/share", status_code=status.HTTP_201_CREATED)
async def share_video(
    video_id: uuid.UUID,
    data: ShareIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Share inside KnowHub: recipients get a notification and a "Shared with me" entry."""
    video = await _visible_video(session, video_id, user)
    try:
        sent = await engagement.share_video(
            session, video, user, data.to_user_ids, data.message, data.at_seconds
        )
    except video_service.VideoError as exc:
        raise _fail(exc) from exc
    return {"shared_with": sent}


@router.get("/shared-with-me", response_model=list[SharedVideo])
async def shared_with_me(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SharedVideo]:
    return [SharedVideo(**item) for item in await engagement.shared_with_me(session, user)]


# ------------------------------------------------------------------ views
@router.post("/videos/{video_id}/view")
async def count_view(
    video_id: uuid.UUID,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Called by the player once playback starts. Open to anonymous viewers."""
    await _visible_video(session, video_id, user)
    return {"view_count": await engagement.count_view(session, video_id)}
