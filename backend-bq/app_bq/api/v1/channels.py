"""Channel pages: the BigQuery twin of app/api/v1/channels.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.video import Channel
from app_bq.api.deps import current_user_optional
from app_bq.core.bq import BigQueryDB, Row, get_db
from app_bq.services import video as video_service

router = APIRouter(tags=["channels"])


@router.get("/channels/{handle}", response_model=Channel)
async def get_channel(
    handle: str,
    user: Row | None = Depends(current_user_optional),
    db: BigQueryDB = Depends(get_db),
) -> Channel:
    """Public to anyone. Viewed by its owner it also returns unlisted, restricted,
    private and still-uploading videos, plus who each restricted video is shared with."""
    try:
        return Channel.model_validate(await video_service.channel_for(db, handle, user))
    except video_service.VideoError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"message": exc.message}) from exc
