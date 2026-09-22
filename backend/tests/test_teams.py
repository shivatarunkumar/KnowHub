"""Teams: the seeded list, filtering the feed, and setting a video's team."""

import uuid

import httpx
import pytest
from sqlalchemy import text

from app.core.db import get_engine
from app.main import app

pytestmark = pytest.mark.integration

FILE = {"file": ("clip.mp4", b"\x00\x00\x00\x20ftypisom" + b"0" * 2048, "video/mp4")}


@pytest.fixture
async def uploader():
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1 FROM teams LIMIT 1"))
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")

    email = f"teams-{uuid.uuid4().hex[:8]}@knowhub.io"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "test-password-123", "display_name": "Team Tester"},
        )
        try:
            yield client
        finally:
            async with get_engine().begin() as conn:
                await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
            await get_engine().dispose()


async def upload(client: httpx.AsyncClient, title: str, **extra) -> dict:
    response = await client.post(
        "/api/v1/videos/upload",
        data={"title": title, "category": "bug_fix", "type": "video", **extra},
        files=FILE,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_teams_are_seeded_and_listed_in_order(uploader):
    teams = (await uploader.get("/api/v1/teams")).json()
    slugs = [t["slug"] for t in teams]
    assert "payments" in slugs and "fraud" in slugs
    assert [t["name"] for t in teams][0] == "Payments"  # sort_order, not alphabetical
    # each carries the division it belongs to, which the filter groups by
    assert {t["division"] for t in teams} >= {"Risk", "Technology"}


async def test_a_video_can_belong_to_a_team(uploader):
    video = await upload(uploader, "Chargeback edge case", team_slug="cards")
    assert video["team_slug"] == "cards"
    assert video["team_name"] == "Cards"

    fetched = (await uploader.get(f"/api/v1/videos/{video['id']}")).json()
    assert fetched["team_name"] == "Cards"


async def test_a_video_without_a_team_is_still_fine(uploader):
    video = await upload(uploader, "No team here")
    assert video["team_slug"] is None


async def test_an_unknown_team_is_refused(uploader):
    response = await uploader.post(
        "/api/v1/videos/upload",
        data={"title": "x", "category": "bug_fix", "type": "video", "team_slug": "not-a-team"},
        files=FILE,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["field"] == "team_slug"


async def test_the_feed_filters_by_team(uploader):
    mine = await upload(uploader, "Sanctions screening timeout", team_slug="fraud")
    other = await upload(uploader, "Ledger close is slow", team_slug="finance")

    fraud = (await uploader.get("/api/v1/videos/feed?team=fraud")).json()["items"]
    ids = [v["id"] for v in fraud]
    assert mine["id"] in ids
    assert other["id"] not in ids

    # no team filter means every team, which is the default the home page uses
    everything = [v["id"] for v in (await uploader.get("/api/v1/videos/feed")).json()["items"]]
    assert mine["id"] in everything and other["id"] in everything


async def test_team_and_topic_filters_combine(uploader):
    match = await upload(uploader, "Fraud rules on BigQuery", team_slug="fraud", topic_slug="bigquery")
    wrong_team = await upload(uploader, "Finance on BigQuery", team_slug="finance", topic_slug="bigquery")

    both = [
        v["id"] for v in (await uploader.get("/api/v1/videos/feed?team=fraud&topic=bigquery")).json()["items"]
    ]
    assert match["id"] in both
    assert wrong_team["id"] not in both


async def test_the_owner_can_change_a_videos_team(uploader):
    video = await upload(uploader, "Moved to another team", team_slug="cards")
    edited = await uploader.patch(f"/api/v1/videos/{video['id']}", json={"team_slug": "payments"})
    assert edited.status_code == 200
    assert edited.json()["team_name"] == "Payments"

    cleared = await uploader.patch(f"/api/v1/videos/{video['id']}", json={"team_slug": ""})
    assert cleared.json()["team_slug"] is None


async def test_the_first_upload_remembers_the_uploaders_team(uploader):
    """So the upload form can default to it next time instead of asking again."""
    before = (await uploader.get("/api/v1/auth/me")).json()
    assert before["team_id"] is None

    started = await uploader.post(
        "/api/v1/videos/uploads/start",
        json={
            "filename": "clip.mp4",
            "content_type": "video/mp4",
            "size": 2048,
            "title": "First upload",
            "category": "how_to",
            "team_slug": "sre",
        },
    )
    assert started.status_code == 201

    after = (await uploader.get("/api/v1/auth/me")).json()
    assert after["team_id"] is not None
