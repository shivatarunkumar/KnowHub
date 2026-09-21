"""Auth tests.

Unit tests always run. The endpoint tests need the KnowHub database (they create and
delete their own users), and are skipped when it isn't reachable.
"""

import uuid

import httpx
import pytest
from sqlalchemy import text

from app.core import security
from app.core.db import get_engine
from app.main import app
from app.services.auth import handle_from_email


# ---------------------------------------------------------------- unit
def test_password_hash_roundtrip():
    hashed = security.hash_password("supersecret123")
    assert hashed != "supersecret123"
    assert security.verify_password("supersecret123", hashed)
    assert not security.verify_password("wrong", hashed)


def test_verify_survives_a_corrupt_hash():
    assert not security.verify_password("anything", "not-a-hash")


def test_access_token_roundtrip():
    from app.core.config import Settings

    settings = Settings(_env_file=None, jwt_secret="x" * 40)
    user_id = uuid.uuid4()
    token = security.create_access_token(settings, user_id, "admin")
    claims = security.decode_access_token(settings, token)
    assert claims and claims["sub"] == str(user_id) and claims["role"] == "admin"


def test_access_token_rejected_with_another_secret():
    from app.core.config import Settings

    signed = Settings(_env_file=None, jwt_secret="a" * 40)
    other = Settings(_env_file=None, jwt_secret="b" * 40)
    token = security.create_access_token(signed, uuid.uuid4(), "user")
    assert security.decode_access_token(other, token) is None


def test_refresh_token_is_only_stored_hashed():
    token, token_hash = security.new_refresh_token()
    assert token != token_hash
    assert security.hash_refresh_token(token) == token_hash
    assert len(token) > 30


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("tarun.nagula@corp.com", "tarun.nagula"),
        ("TARUN@corp.com", "tarun"),
        ("a@corp.com", "auser"),
        ("weird!!name+tag@corp.com", "weirdnametag"),
    ],
)
def test_handle_from_email(email, expected):
    assert handle_from_email(email) == expected


# ---------------------------------------------------------------- endpoints
pytestmark_integration = pytest.mark.integration


@pytest.fixture
async def client():
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1 FROM users LIMIT 1"))
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await get_engine().dispose()


@pytest.fixture
def account():
    email = f"test-{uuid.uuid4().hex[:10]}@knowhub.io"
    yield {"email": email, "password": "test-password-123", "display_name": "Test User"}


async def delete_account(email: str) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})


@pytest.mark.integration
async def test_register_login_refresh_logout(client, account):
    try:
        created = await client.post("/api/v1/auth/register", json=account)
        assert created.status_code == 201, created.text
        assert created.json()["handle"].startswith("test-")
        assert "knowhub_access" in created.cookies

        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == account["email"]

        duplicate = await client.post("/api/v1/auth/register", json=account)
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["field"] == "email"

        # the email is matched case-insensitively
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": account["email"].upper(), "password": account["password"]},
        )
        assert login.status_code == 200

        wrong = await client.post(
            "/api/v1/auth/login", json={"email": account["email"], "password": "not-it"}
        )
        assert wrong.status_code == 401
        assert wrong.json()["detail"]["message"] == "Incorrect email or password"

        refreshed = await client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200

        assert (await client.post("/api/v1/auth/logout")).status_code == 204
        assert (await client.get("/api/v1/auth/me")).status_code == 401
    finally:
        await delete_account(account["email"])


@pytest.mark.integration
async def test_unknown_email_and_wrong_password_look_identical(client, account):
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody-here@knowhub.io", "password": "whatever-123"}
    )
    assert unknown.status_code == 401
    assert unknown.json()["detail"]["message"] == "Incorrect email or password"


@pytest.mark.integration
async def test_reusing_a_rotated_refresh_token_ends_the_session(client, account):
    try:
        await client.post("/api/v1/auth/register", json=account)
        stolen = client.cookies.get("knowhub_refresh")

        assert (await client.post("/api/v1/auth/refresh")).status_code == 200  # rotates

        client.cookies.set("knowhub_refresh", stolen)
        replayed = await client.post("/api/v1/auth/refresh")
        assert replayed.status_code == 401

        # every session for that user is revoked, so the new token is dead too
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    finally:
        await delete_account(account["email"])
