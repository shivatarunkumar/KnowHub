"""Engagement tests: likes, comments, replies, sharing and views.

These run against the KnowHub database (they create and remove their own users and
video) and are skipped when it isn't reachable.
"""

import uuid

import httpx
import pytest
from sqlalchemy import text

from app.core.db import get_engine
from app.main import app

pytestmark = pytest.mark.integration


async def new_client(email: str) -> httpx.AsyncClient:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "test-password-123", "display_name": email.split("@")[0]},
    )
    return client


@pytest.fixture
async def people():
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1 FROM videos LIMIT 1"))
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")

    suffix = uuid.uuid4().hex[:8]
    owner_email, viewer_email = f"owner-{suffix}@knowhub.io", f"viewer-{suffix}@knowhub.io"
    owner, viewer = await new_client(owner_email), await new_client(viewer_email)

    created = await owner.post(
        "/api/v1/videos/upload",
        data={"title": "Engagement fixture", "category": "how_to", "type": "video"},
        files={"file": ("clip.mp4", b"\x00\x00\x00\x20ftypisom" + b"0" * 2048, "video/mp4")},
    )
    video_id = created.json()["id"]
    try:
        yield owner, viewer, video_id
    finally:
        await owner.aclose()
        await viewer.aclose()
        async with get_engine().begin() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE email IN (:a, :b)"), {"a": owner_email, "b": viewer_email}
            )
        await get_engine().dispose()


async def test_like_dislike_and_clear(people):
    _, viewer, video_id = people

    liked = await viewer.put(f"/api/v1/videos/{video_id}/reaction", json={"value": 1})
    assert liked.json() == {"like_count": 1, "dislike_count": 0, "my_reaction": 1}

    disliked = await viewer.put(f"/api/v1/videos/{video_id}/reaction", json={"value": -1})
    assert disliked.json() == {"like_count": 0, "dislike_count": 1, "my_reaction": -1}

    cleared = await viewer.put(f"/api/v1/videos/{video_id}/reaction", json={"value": 0})
    assert cleared.json() == {"like_count": 0, "dislike_count": 0, "my_reaction": 0}


async def test_anonymous_can_read_but_not_react(people):
    _, _, video_id = people
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as guest:
        assert (await guest.get(f"/api/v1/videos/{video_id}/reaction")).status_code == 200
        assert (await guest.put(f"/api/v1/videos/{video_id}/reaction", json={"value": 1})).status_code == 401


async def test_comment_reply_and_like(people):
    owner, viewer, video_id = people

    posted = await viewer.post(f"/api/v1/videos/{video_id}/comments", json={"body": "Does this cover GKE?"})
    assert posted.status_code == 201
    comment_id = posted.json()["id"]

    reply = await owner.post(
        f"/api/v1/videos/{video_id}/comments", json={"body": "Yes it does.", "parent_id": comment_id}
    )
    assert reply.status_code == 201

    liked = await owner.put(f"/api/v1/comments/{comment_id}/reaction")
    assert liked.json() == {"like_count": 1, "liked_by_me": True}
    unliked = await owner.put(f"/api/v1/comments/{comment_id}/reaction")
    assert unliked.json() == {"like_count": 0, "liked_by_me": False}

    thread = (await viewer.get(f"/api/v1/videos/{video_id}/comments")).json()
    assert len(thread) == 1
    assert thread[0]["is_mine"] is True
    assert len(thread[0]["replies"]) == 1
    assert thread[0]["replies"][0]["is_uploader"] is True


async def test_replies_never_nest_deeper_than_one_level(people):
    owner, viewer, video_id = people
    top = (await viewer.post(f"/api/v1/videos/{video_id}/comments", json={"body": "top"})).json()
    reply = (
        await owner.post(
            f"/api/v1/videos/{video_id}/comments", json={"body": "reply", "parent_id": top["id"]}
        )
    ).json()
    deeper = (
        await viewer.post(
            f"/api/v1/videos/{video_id}/comments", json={"body": "deeper", "parent_id": reply["id"]}
        )
    ).json()
    assert deeper["parent_id"] == top["id"]  # attached to the thread, not to the reply


async def test_only_author_or_uploader_can_delete(people):
    owner, viewer, video_id = people
    mine = (await owner.post(f"/api/v1/videos/{video_id}/comments", json={"body": "uploader note"})).json()

    assert (await viewer.delete(f"/api/v1/comments/{mine['id']}")).status_code == 403
    assert (await owner.delete(f"/api/v1/comments/{mine['id']}")).status_code == 204
    assert (await viewer.get(f"/api/v1/videos/{video_id}/comments")).json() == []


async def test_share_reaches_the_recipient(people):
    owner, viewer, video_id = people
    me = (await viewer.get("/api/v1/auth/me")).json()

    shared = await owner.post(
        f"/api/v1/videos/{video_id}/share",
        json={"to_user_ids": [me["id"]], "message": "relevant to your incident"},
    )
    assert shared.status_code == 201
    assert shared.json() == {"shared_with": 1}

    inbox = (await viewer.get("/api/v1/shared-with-me")).json()
    assert inbox[0]["video_id"] == video_id
    assert inbox[0]["message"] == "relevant to your incident"


async def test_view_count_increments(people):
    _, viewer, video_id = people
    first = (await viewer.post(f"/api/v1/videos/{video_id}/view")).json()["view_count"]
    second = (await viewer.post(f"/api/v1/videos/{video_id}/view")).json()["view_count"]
    assert second == first + 1


async def test_comment_can_be_edited_within_the_window(people):
    _, viewer, video_id = people
    posted = (
        await viewer.post(f"/api/v1/videos/{video_id}/comments", json={"body": "helful, thanks"})
    ).json()

    edited = await viewer.patch(f"/api/v1/comments/{posted['id']}", json={"body": "Helpful, thanks."})
    assert edited.status_code == 200
    assert edited.json()["body"] == "Helpful, thanks."
    assert edited.json()["edited_at"] is not None


async def test_comment_cannot_be_edited_after_the_window(people):
    _, viewer, video_id = people
    posted = (await viewer.post(f"/api/v1/videos/{video_id}/comments", json={"body": "typo"})).json()

    async with get_engine().begin() as conn:  # pretend it was written two minutes ago
        await conn.execute(
            text("UPDATE comments SET created_at = now() - interval '2 minutes' WHERE id = :id"),
            {"id": posted["id"]},
        )

    late = await viewer.patch(f"/api/v1/comments/{posted['id']}", json={"body": "too late"})
    assert late.status_code == 403
    assert "60 seconds" in late.json()["detail"]["message"]


async def test_only_the_author_can_edit(people):
    owner, viewer, video_id = people
    posted = (await viewer.post(f"/api/v1/videos/{video_id}/comments", json={"body": "mine"})).json()
    assert (await owner.patch(f"/api/v1/comments/{posted['id']}", json={"body": "yours"})).status_code == 403


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("thanks @tarun this helped", ["tarun"]),
        ("@alice and @bob, see this", ["alice", "bob"]),
        ("@alice @alice twice", ["alice"]),
        ("email me at name@example.com", []),  # not a mention
        ("ask @tarun.nagula14.", ["tarun.nagula14"]),  # trailing full stop isn't part of it
        ("@ab is too short", []),
        ("no mentions here", []),
    ],
)
def test_mentioned_handles(body, expected):
    from app.services.engagement import mentioned_handles

    assert mentioned_handles(body) == expected


async def test_mention_notifies_that_person(people):
    owner, viewer, video_id = people
    owner_handle = (await owner.get("/api/v1/auth/me")).json()["handle"]
    viewer_id = (await viewer.get("/api/v1/auth/me")).json()["id"]

    await viewer.post(
        f"/api/v1/videos/{video_id}/comments", json={"body": f"@{owner_handle} does this cover GKE?"}
    )

    async with get_engine().connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT type FROM notifications WHERE actor_id = :actor AND type = 'comment_mention'"),
                {"actor": viewer_id},
            )
        ).all()
    assert len(rows) == 1


async def test_mentioning_yourself_notifies_nobody(people):
    _, viewer, video_id = people
    me = (await viewer.get("/api/v1/auth/me")).json()

    await viewer.post(f"/api/v1/videos/{video_id}/comments", json={"body": f"note to self @{me['handle']}"})

    async with get_engine().connect() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM notifications WHERE user_id = :me"), {"me": me["id"]}
            )
        ).scalar_one()
    assert count == 0


async def test_upload_keeps_links_and_snippets(people):
    owner, _, _ = people
    started = await owner.post(
        "/api/v1/videos/uploads/start",
        json={
            "filename": "clip.mp4",
            "content_type": "video/mp4",
            "size": 1024,
            "title": "With resources",
            "category": "how_to",
            "links": [{"kind": "confluence", "url": "https://wiki.example.com/page", "label": "Runbook"}],
            "snippets": [{"title": "Create", "language": "bash", "code": "bq mk --table x"}],
        },
    )
    assert started.status_code == 201
    video_id = started.json()["video_id"]

    async with get_engine().connect() as conn:
        links = (
            await conn.execute(
                text("SELECT kind, url FROM video_links WHERE video_id = :id"), {"id": video_id}
            )
        ).all()
        snippets = (
            await conn.execute(
                text("SELECT language, code FROM video_snippets WHERE video_id = :id"), {"id": video_id}
            )
        ).all()
    assert links == [("confluence", "https://wiki.example.com/page")]
    assert snippets == [("bash", "bq mk --table x")]


async def test_thumbnail_upload_serve_and_permissions(people):
    owner, viewer, video_id = people

    assert (await viewer.get(f"/api/v1/videos/{video_id}/thumbnail")).status_code == 404

    jpeg = ("file", ("t.jpg", b"\xff\xd8\xff\xe0" + b"0" * 512, "image/jpeg"))
    uploaded = await owner.post(f"/api/v1/videos/{video_id}/thumbnail", files=dict([jpeg]))
    assert uploaded.status_code == 204

    served = await viewer.get(f"/api/v1/videos/{video_id}/thumbnail")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert (await viewer.get(f"/api/v1/videos/{video_id}")).json()["has_thumbnail"] is True

    # not your video
    assert (await viewer.post(f"/api/v1/videos/{video_id}/thumbnail", files=dict([jpeg]))).status_code == 403
    # not an image
    assert (
        await owner.post(
            f"/api/v1/videos/{video_id}/thumbnail",
            files={"file": ("t.pdf", b"%PDF-1.4", "application/pdf")},
        )
    ).status_code == 400


async def test_browser_measured_duration_is_kept(people):
    owner, _, _ = people
    started = await owner.post(
        "/api/v1/videos/uploads/start",
        json={
            "filename": "clip.mp4",
            "content_type": "video/mp4",
            "size": 2048,
            "title": "With duration",
            "category": "demo",
            "duration_sec": 137,
            "width": 1920,
            "height": 1080,
        },
    )
    video_id = started.json()["video_id"]
    async with get_engine().connect() as conn:
        row = (
            await conn.execute(
                text("SELECT duration_sec, width, height FROM videos WHERE id = :id"), {"id": video_id}
            )
        ).one()
    assert row == (137, 1920, 1080)
