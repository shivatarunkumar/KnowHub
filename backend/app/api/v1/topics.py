import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.topic import Topic

router = APIRouter(prefix="/topics", tags=["topics"])


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    icon: str | None


@router.get("", response_model=list[TopicOut])
async def list_topics(session: AsyncSession = Depends(get_session)) -> list[Topic]:
    """Active topics in display order (home page chips, sidebar, upload form)."""
    result = await session.execute(
        select(Topic).where(Topic.is_active).order_by(Topic.sort_order, Topic.name)
    )
    return list(result.scalars())
