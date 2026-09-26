"""Topics: the BigQuery twin of app/api/v1/topics.py."""

from fastapi import APIRouter, Depends

from app.api.v1.topics import TopicOut
from app_bq.core.bq import BigQueryDB, get_db

router = APIRouter(prefix="/topics", tags=["topics"])

TOPICS_SQL = """
WITH counts AS (
  SELECT primary_topic_id AS topic_id, COUNT(*) AS videos FROM {videos}
  WHERE deleted_at IS NULL AND status = 'READY' AND visibility = 'internal'
  GROUP BY primary_topic_id)
SELECT t.*, COALESCE(c.videos, 0) AS video_count
FROM {topics} AS t LEFT JOIN counts AS c ON c.topic_id = t.id
WHERE t.is_active
ORDER BY t.sort_order, t.name
"""


@router.get("", response_model=list[TopicOut])
async def list_topics(db: BigQueryDB = Depends(get_db)) -> list[TopicOut]:
    """Active topics in display order, each with the number of videos anyone can watch."""
    return [TopicOut.model_validate(row) for row in await db.rows(TOPICS_SQL)]
