import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.topic import Topic
from app.models.video import Video

router = APIRouter(prefix="/topics", tags=["topics"])


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    icon: str | None
    # how many published videos are filed under it, so the UI can lead with the ones
    # that have something to show instead of listing all of them equally
    video_count: int = 0


@router.get("", response_model=list[TopicOut])
async def list_topics(session: AsyncSession = Depends(get_session)) -> list[TopicOut]:
    """Active topics in display order, each with the number of videos anyone can watch."""
    counts = (
        select(Video.primary_topic_id.label("topic_id"), func.count().label("videos"))
        .where(
            Video.deleted_at.is_(None),
            Video.status == "READY",
            Video.visibility == "internal",
        )
        .group_by(Video.primary_topic_id)
        .subquery()
    )
    rows = await session.execute(
        select(Topic, func.coalesce(counts.c.videos, 0))
        .outerjoin(counts, counts.c.topic_id == Topic.id)
        .where(Topic.is_active)
        .order_by(Topic.sort_order, Topic.name)
    )
    return [
        TopicOut(**{c.name: getattr(topic, c.name) for c in topic.__table__.columns}, video_count=count)
        for topic, count in rows
    ]
