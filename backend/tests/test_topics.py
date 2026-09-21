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
    assert slugs[:3] == ["bigquery", "pubsub", "gke"]
