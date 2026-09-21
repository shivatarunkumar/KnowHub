import httpx
import pytest

from app.main import app
from app.services import health


def fake(result=None, error=None):
    async def check(settings):
        if error:
            raise error
        return result

    return check


@pytest.fixture
def client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def patch_checks(monkeypatch):
    def apply(**checks):
        for name, check in checks.items():
            monkeypatch.setitem(health.CHECKS, name, check)

    return apply


OK = fake({"ok": True})


async def test_liveness(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_all_ok(client, patch_checks):
    patch_checks(database=OK, storage=OK, pubsub=OK, ai=OK)
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_ai_failure_is_degraded_not_down(client, patch_checks):
    patch_checks(database=OK, storage=OK, pubsub=OK, ai=fake(error=ConnectionError("refused")))
    response = await client.get("/api/v1/health")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "degraded"
    assert "refused" in body["checks"]["ai"]["error"]


async def test_required_failure_is_503(client, patch_checks):
    patch_checks(database=fake({"ok": False}), storage=OK, pubsub=OK, ai=OK)
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["status"] == "down"


async def test_slow_check_times_out(client, patch_checks, monkeypatch):
    import asyncio

    async def slow(settings):
        await asyncio.sleep(1)

    monkeypatch.setattr(health, "CHECK_TIMEOUT_SECONDS", 0.05)
    patch_checks(database=OK, storage=slow, pubsub=OK, ai=OK)
    body = (await client.get("/api/v1/health")).json()
    assert body["status"] == "down"
    assert "timed out" in body["checks"]["storage"]["error"]
