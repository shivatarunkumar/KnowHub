"""Integration test: needs the migrated + seeded compose Postgres (skipped otherwise)."""

import httpx
import pytest
from sqlalchemy import text

from app.core.db import get_engine
from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
async def db_available():
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1 FROM topics LIMIT 1"))
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")
    finally:
        await get_engine().dispose()


async def test_lists_seeded_topics_in_order(db_available):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/topics")
    await get_engine().dispose()
    assert response.status_code == 200
    slugs = [t["slug"] for t in response.json()]
    # "gcp" is the umbrella topic and sorts above the individual services
    assert slugs[:4] == ["gcp", "bigquery", "pubsub", "gke"]


async def test_topics_carry_a_video_count(db_available):
    """The chip bar leads with the topics that have something in them, so the count has
    to come from the API rather than being guessed in the browser."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        topics = (await client.get("/api/v1/topics")).json()
    await get_engine().dispose()

    assert all("video_count" in topic for topic in topics)
    assert all(isinstance(topic["video_count"], int) for topic in topics)
    # a freshly seeded topic nobody has filed anything under counts zero, not null
    assert any(topic["video_count"] == 0 for topic in topics)
