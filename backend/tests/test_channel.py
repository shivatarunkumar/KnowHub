"""Channel management: editing, who can see a video, comments on or off, deleting.

These run against the KnowHub database (they create and remove their own users and
videos) and are skipped when it isn't reachable.
"""

import uuid

import httpx
import pytest
from sqlalchemy import text

from app.core.db import get_engine
from app.main import app

pytestmark = pytest.mark.integration

FILE = {"file": ("clip.mp4", b"\x00\x00\x00\x20ftypisom" + b"0" * 2048, "video/mp4")}


async def new_client(email: str) -> httpx.AsyncClient:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "test-password-123", "display_name": email.split("@")[0]},
    )
    return client


@pytest.fixture
async def channel():
    """An owner with one video, a colleague and a stranger."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT comments_enabled FROM videos LIMIT 1"))
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")

    suffix = uuid.uuid4().hex[:8]
    emails = [f"{who}-{suffix}@knowhub.io" for who in ("owner", "mate", "other")]
    owner, mate, other = [await new_client(email) for email in emails]

    me = (await owner.get("/api/v1/auth/me")).json()
    mate_me = (await mate.get("/api/v1/auth/me")).json()
    created = await owner.post(
        "/api/v1/videos/upload",
        data={"title": "Channel fixture", "category": "how_to", "type": "video"},
        files=FILE,
    )
    video_id = created.json()["id"]
    try:
        yield {
            "owner": owner,
            "mate": mate,
            "other": other,
            "handle": me["handle"],
            "mate_id": mate_me["id"],
            "video_id": video_id,
        }
    finally:
        for client in (owner, mate, other):
            await client.aclose()
        async with get_engine().begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE email = ANY(:emails)"), {"emails": emails})
        await get_engine().dispose()


async def test_channel_shows_my_videos_to_me_and_to_visitors(channel):
    handle, video_id = channel["handle"], channel["video_id"]

    mine = (await channel["owner"].get(f"/api/v1/channels/{handle}")).json()
    assert mine["is_me"] is True
    assert [v["id"] for v in mine["videos"]] == [video_id]

    theirs = (await channel["other"].get(f"/api/v1/channels/{handle}")).json()
    assert theirs["is_me"] is False
    assert theirs["video_count"] == 1
    # only the owner is told who a video is shared with
    assert "allowed_viewers" not in theirs["videos"][0] or theirs["videos"][0]["allowed_viewers"] == []

    assert (await channel["owner"].get("/api/v1/channels/nobody-here")).status_code == 404


async def test_owner_edits_wording(channel):
    owner, video_id = channel["owner"], channel["video_id"]

    edited = await owner.patch(
        f"/api/v1/videos/{video_id}",
        json={"title": "Fixing consumer lag", "description": "Raise max.poll.interval.ms."},
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Fixing consumer lag"
    assert edited.json()["description"] == "Raise max.poll.interval.ms."

    # untouched fields stay as they were
    assert edited.json()["category"] == "how_to"

    refused = await channel["other"].patch(f"/api/v1/videos/{video_id}", json={"title": "Mine now"})
    assert refused.status_code == 403


async def test_hiding_a_video_removes_it_from_everyone_else(channel):
    owner, other, video_id = channel["owner"], channel["other"], channel["video_id"]

    hidden = await owner.patch(f"/api/v1/videos/{video_id}", json={"visibility": "private"})
    assert hidden.status_code == 200

    assert (await other.get(f"/api/v1/videos/{video_id}")).status_code == 404
    assert video_id not in [v["id"] for v in (await other.get("/api/v1/videos/feed")).json()["items"]]
    assert (await other.get(f"/api/v1/channels/{channel['handle']}")).json()["video_count"] == 0

    # the owner still sees it, on the watch page and in their channel
    assert (await owner.get(f"/api/v1/videos/{video_id}")).status_code == 200
    assert (await owner.get(f"/api/v1/channels/{channel['handle']}")).json()["video_count"] == 1


async def test_restricting_a_video_to_a_few_people(channel):
    owner, mate, other = channel["owner"], channel["mate"], channel["other"]
    video_id = channel["video_id"]

    saved = await owner.patch(
        f"/api/v1/videos/{video_id}",
        json={"visibility": "restricted", "viewer_ids": [channel["mate_id"]]},
    )
    assert saved.status_code == 200

    assert (await mate.get(f"/api/v1/videos/{video_id}")).status_code == 200
    assert (await other.get(f"/api/v1/videos/{video_id}")).status_code == 404
    # an anonymous visitor can't watch it either
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as guest:
        assert (await guest.get(f"/api/v1/videos/{video_id}")).status_code == 404

    listed = (await owner.get(f"/api/v1/channels/{channel['handle']}")).json()["videos"][0]
    assert [p["id"] for p in listed["allowed_viewers"]] == [channel["mate_id"]]

    # taking the person off the list takes the video away again
    await owner.patch(f"/api/v1/videos/{video_id}", json={"viewer_ids": []})
    assert (await mate.get(f"/api/v1/videos/{video_id}")).status_code == 404


async def test_turning_comments_off(channel):
    owner, other, video_id = channel["owner"], channel["other"], channel["video_id"]

    posted = await other.post(f"/api/v1/videos/{video_id}/comments", json={"body": "Helpful, thanks!"})
    assert posted.status_code == 201

    await owner.patch(f"/api/v1/videos/{video_id}", json={"comments_enabled": False})

    refused = await other.post(f"/api/v1/videos/{video_id}/comments", json={"body": "One more thing"})
    assert refused.status_code == 403
    assert (await owner.get(f"/api/v1/videos/{video_id}")).json()["comments_enabled"] is False
    # comments already posted stay readable
    assert len((await other.get(f"/api/v1/videos/{video_id}/comments")).json()) == 1

    await owner.patch(f"/api/v1/videos/{video_id}", json={"comments_enabled": True})
    again = await other.post(f"/api/v1/videos/{video_id}/comments", json={"body": "back on"})
    assert again.status_code == 201


async def test_deleting_a_video(channel):
    owner, other, video_id = channel["owner"], channel["other"], channel["video_id"]

    assert (await other.delete(f"/api/v1/videos/{video_id}")).status_code == 403
    assert (await owner.delete(f"/api/v1/videos/{video_id}")).status_code == 204

    assert (await owner.get(f"/api/v1/videos/{video_id}")).status_code == 404
    assert (await owner.get(f"/api/v1/channels/{channel['handle']}")).json()["video_count"] == 0
    # the audit trail keeps the record of what happened
    async with get_engine().connect() as conn:
        events = (
            (
                await conn.execute(
                    text("SELECT event FROM upload_events WHERE video_id = :id"), {"id": video_id}
                )
            )
            .scalars()
            .all()
        )
    assert "deleted" in events


async def test_owner_can_replace_links_and_snippets(channel):
    owner, video_id = channel["owner"], channel["video_id"]

    await owner.patch(
        f"/api/v1/videos/{video_id}",
        json={
            "links": [{"kind": "confluence", "url": "https://wiki.example.com/runbook"}],
            "snippets": [{"title": "Fix", "language": "bash", "code": "kubectl rollout restart"}],
        },
    )
    body = (await owner.get(f"/api/v1/videos/{video_id}")).json()
    assert [link["url"] for link in body["links"]] == ["https://wiki.example.com/runbook"]
    assert [s["code"] for s in body["snippets"]] == ["kubectl rollout restart"]

    await owner.patch(f"/api/v1/videos/{video_id}", json={"links": []})
    after = (await owner.get(f"/api/v1/videos/{video_id}")).json()
    assert after["links"] == []
    assert len(after["snippets"]) == 1  # snippets weren't sent, so they stayed
