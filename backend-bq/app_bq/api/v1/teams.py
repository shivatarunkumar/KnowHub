"""Teams: the BigQuery twin of app/api/v1/teams.py."""

from fastapi import APIRouter, Depends

from app.api.v1.teams import TeamOut
from app_bq.core.bq import BigQueryDB, Row, get_db

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamOut])
async def list_teams(db: BigQueryDB = Depends(get_db)) -> list[Row]:
    """Active teams in display order (home filter, sidebar, upload form)."""
    return await db.rows("SELECT * FROM {teams} WHERE is_active ORDER BY sort_order, name")
