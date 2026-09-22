import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.team import Team

router = APIRouter(prefix="/teams", tags=["teams"])


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    division: str | None


@router.get("", response_model=list[TeamOut])
async def list_teams(session: AsyncSession = Depends(get_session)) -> list[Team]:
    """Active teams in display order (home filter, sidebar, upload form)."""
    result = await session.execute(select(Team).where(Team.is_active).order_by(Team.sort_order, Team.name))
    return list(result.scalars())
