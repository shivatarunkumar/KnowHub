"""Forgotten-password flow: request a link, use it once, sign in with the new password."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text

from app.core.db import get_engine
from app.main import app

pytestmark = pytest.mark.integration

PASSWORD = "test-password-123"


@pytest.fixture
async def account():
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1 FROM password_reset_tokens LIMIT 1"))
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")

    email = f"reset-{uuid.uuid4().hex[:8]}@knowhub.io"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": PASSWORD, "display_name": "Reset Tester"},
        )
        try:
            yield client, email
        finally:
            async with get_engine().begin() as conn:
                await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
            await get_engine().dispose()


async def request_link(client: httpx.AsyncClient, email: str) -> str | None:
    response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert response.status_code == 202
    return response.json()["reset_url"]


def token_of(url: str) -> str:
    return url.split("token=", 1)[1]


async def test_unknown_email_looks_exactly_like_a_known_one(account):
    client, email = account
    known = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    unknown = await client.post(
        "/api/v1/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex}@knowhub.io"}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json()["message"] == unknown.json()["message"]
    # the link is what differs, and it is only ever sent for a real account
    assert known.json()["reset_url"] and unknown.json()["reset_url"] is None


async def test_reset_then_sign_in_with_the_new_password(account):
    client, email = account
    token = token_of(await request_link(client, email))

    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "brand-new-password"}
    )
    assert reset.status_code == 204

    old = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert old.status_code == 401
    new = await client.post("/api/v1/auth/login", json={"email": email, "password": "brand-new-password"})
    assert new.status_code == 200


async def test_a_link_works_once(account):
    client, email = account
    token = token_of(await request_link(client, email))
    assert (
        await client.post("/api/v1/auth/reset-password", json={"token": token, "password": "first-password"})
    ).status_code == 204
    again = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "second-password"}
    )
    assert again.status_code == 400
    assert "no longer valid" in again.json()["detail"]["message"]


async def test_asking_again_invalidates_the_previous_link(account):
    client, email = account
    first = token_of(await request_link(client, email))
    second = token_of(await request_link(client, email))

    stale = await client.post("/api/v1/auth/reset-password", json={"token": first, "password": "abcdefgh1"})
    assert stale.status_code == 400
    fresh = await client.post("/api/v1/auth/reset-password", json={"token": second, "password": "abcdefgh1"})
    assert fresh.status_code == 204


async def test_expired_links_are_refused(account):
    client, email = account
    token = token_of(await request_link(client, email))
    # age the whole row: the table's CHECK keeps expires_at after created_at, so a link
    # can only be expired by having been issued long enough ago
    async with get_engine().begin() as conn:
        await conn.execute(
            text("UPDATE password_reset_tokens SET created_at = :issued, expires_at = :expired"),
            {
                "issued": datetime.now(UTC) - timedelta(minutes=45),
                "expired": datetime.now(UTC) - timedelta(minutes=15),
            },
        )
    refused = await client.post("/api/v1/auth/reset-password", json={"token": token, "password": "abcdefgh1"})
    assert refused.status_code == 400


async def test_a_made_up_token_is_refused(account):
    client, _ = account
    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": "x" * 43, "password": "abcdefgh1"}
    )
    assert response.status_code == 400


async def test_reset_signs_other_sessions_out(account):
    client, email = account
    # a second device, signed in with the original password
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as other:
        await other.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert (await other.get("/api/v1/auth/me")).status_code == 200

        token = token_of(await request_link(client, email))
        await client.post("/api/v1/auth/reset-password", json={"token": token, "password": "abcdefgh1"})

        # its refresh token was revoked, so it cannot get a new access token
        assert (await other.post("/api/v1/auth/refresh")).status_code == 401


async def test_short_passwords_are_rejected(account):
    client, email = account
    token = token_of(await request_link(client, email))
    assert (
        await client.post("/api/v1/auth/reset-password", json={"token": token, "password": "short"})
    ).status_code == 422
