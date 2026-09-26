"""AI writing assist: the BigQuery twin of app/api/v1/ai.py (same request and response)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.ai import EnhanceIn, EnhanceOut, OutcomeIn
from app.core.config import Settings, get_settings
from app_bq.api.deps import current_user
from app_bq.core.bq import BigQueryDB, Row, get_db
from app_bq.services import ai_assist

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/enhance", response_model=EnhanceOut)
async def enhance(
    data: EnhanceIn,
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> EnhanceOut:
    """Rewrite a title or description, or suggest tags. Nothing is saved: the author
    decides whether to keep the suggestion."""
    try:
        result = await ai_assist.enhance(
            db, settings, user_id=user.id, field=data.field, text=data.text, context=data.context.model_dump()
        )
    except ai_assist.AssistError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"message": exc.message}) from exc
    return EnhanceOut(**result)


@router.post("/enhance/outcome", status_code=204)
async def outcome(
    data: OutcomeIn,
    user: Row = Depends(current_user),
    db: BigQueryDB = Depends(get_db),
) -> None:
    """Tell us whether the suggestion was kept, so we can tell if the prompts work."""
    await db.update("ai_requests", {"id": data.request_id}, {"accepted": data.accepted})
