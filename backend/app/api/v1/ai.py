"""AI writing assist for the upload form."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.models.user import User
from app.services import ai_assist

router = APIRouter(prefix="/ai", tags=["ai"])


class EnhanceContext(BaseModel):
    title: str | None = None
    topic: str | None = None
    category: str | None = None
    type: str | None = None


class EnhanceIn(BaseModel):
    field: str = Field(description="title | description | tags")
    text: str
    context: EnhanceContext = EnhanceContext()


class EnhanceOut(BaseModel):
    field: str
    suggestion: str
    request_id: str
    # which model actually wrote this, so the box can say so
    provider: str
    model: str
    items: list[str] | None = None


class OutcomeIn(BaseModel):
    request_id: uuid.UUID
    accepted: bool


@router.post("/enhance", response_model=EnhanceOut)
async def enhance(
    data: EnhanceIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> EnhanceOut:
    """Rewrite a title or description, or suggest tags. Nothing is saved: the author
    decides whether to keep the suggestion."""
    try:
        result = await ai_assist.enhance(
            session,
            settings,
            user_id=user.id,
            field=data.field,
            text=data.text,
            context=data.context.model_dump(),
        )
    except ai_assist.AssistError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"message": exc.message}) from exc
    return EnhanceOut(**result)


@router.post("/enhance/outcome", status_code=204)
async def outcome(
    data: OutcomeIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Tell us whether the suggestion was kept, so we can tell if the prompts work."""
    await ai_assist.record_outcome(session, data.request_id, data.accepted)
