"""Channel pages: someone's uploads, and the controls the owner gets over them."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_optional
from app.core.db import get_session
from app.models.user import User
from app.schemas.video import Channel
from app.services import video as video_service

router = APIRouter(tags=["channels"])


@router.get("/channels/{handle}", response_model=Channel)
async def get_channel(
    handle: str,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> Channel:
    """Public to anyone. Viewed by its owner it also returns unlisted, restricted,
    private and still-uploading videos, plus who each restricted video is shared with."""
    try:
        return Channel.model_validate(await video_service.channel_for(session, handle, user))
    except video_service.VideoError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"message": exc.message}) from exc
