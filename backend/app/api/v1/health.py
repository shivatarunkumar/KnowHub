from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.services import health

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    env: str
    checks: dict[str, dict]


@router.get("/health", response_model=HealthResponse)
async def get_health(response: Response, settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Readiness: checks database, storage, Pub/Sub and AI. 503 if a required one is down."""
    status, checks = await health.run_checks(settings)
    if status == "down":
        response.status_code = 503
    return HealthResponse(status=status, env=settings.app_env, checks=checks)
