from fastapi import APIRouter, Depends, Response

from app.api.v1.health import HealthResponse
from app.core.config import Settings, get_settings
from app_bq.services import health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(response: Response, settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Readiness: BigQuery, storage, Pub/Sub and AI. 503 if a required one is down."""
    status, checks = await health.run_checks(settings)
    if status == "down":
        response.status_code = 503
    return HealthResponse(status=status, env=settings.app_env, checks=checks)
