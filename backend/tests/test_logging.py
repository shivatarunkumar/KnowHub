"""Logging: the request line, the request id, and the reason behind a 401."""

import json
import logging

import httpx
import pytest

from app.core.config import Settings
from app.core.db import get_engine
from app.core.logging import JsonFormatter, TextFormatter, configure_logging, request_id_var, user_var
from app.main import app


@pytest.fixture(autouse=True)
async def dispose_engine():
    """These tests call the app, which opens a database engine bound to this test's event
    loop. Leaving it cached makes the next test file fail its connection check."""
    yield
    await get_engine().dispose()


def record(level: int = logging.INFO, message: str = "hello", **extra) -> logging.LogRecord:
    made = logging.LogRecord("knowhub.test", level, __file__, 1, message, (), None)
    made.request_id = request_id_var.get() or "-"
    made.user = user_var.get() or "anonymous"
    for key, value in extra.items():
        setattr(made, key, value)
    return made


def test_text_lines_carry_the_request_and_user(monkeypatch):
    request_id_var.set("abc12345")
    user_var.set("tarun")
    line = TextFormatter().format(record(message="upload started"))
    assert "abc12345" in line and "tarun" in line and "upload started" in line
    assert "INFO" in line


def test_json_output_keeps_extras_as_fields():
    request_id_var.set("abc12345")
    user_var.set("tarun")
    parsed = json.loads(JsonFormatter().format(record(status=401, duration_ms=12)))
    assert parsed["severity"] == "INFO"
    assert parsed["request_id"] == "abc12345"
    assert parsed["user"] == "tarun"
    # extras survive as their own keys, which is the point of the json format
    assert parsed["status"] == 401 and parsed["duration_ms"] == 12


def test_log_level_is_case_insensitive():
    assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"


def test_configure_logging_applies_the_level_and_quiets_the_noise():
    configure_logging(Settings(_env_file=None, log_level="DEBUG"))
    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("uvicorn.access").disabled  # our line replaces it
    assert logging.getLogger("httpx").level >= logging.WARNING
    # SQL is opt-in, however verbose the app log is
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
    configure_logging(Settings(_env_file=None))  # back to INFO for the other tests


async def test_every_response_carries_a_request_id():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/healthz")
    assert len(response.headers["x-request-id"]) == 8


async def test_an_id_from_upstream_is_kept():
    """A proxy or another service can set it, so one trace spans both."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/healthz", headers={"x-request-id": "from-upstream"})
    assert response.headers["x-request-id"] == "from-upstream"


async def test_a_401_says_why_in_the_log(caplog):
    """The log has to answer "why did my upload 401?" without a debugger."""
    with caplog.at_level(logging.INFO, logger="knowhub.auth"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/videos/uploads/start",
                json={
                    "filename": "x.mp4",
                    "content_type": "video/mp4",
                    "size": 10,
                    "title": "t",
                    "category": "how_to",
                },
            )
    assert response.status_code == 401
    assert any("knowhub_access" in r.message for r in caplog.records)
    assert any("/auth/refresh" in r.message for r in caplog.records)


async def test_the_request_line_records_the_outcome(caplog):
    with caplog.at_level(logging.INFO, logger="knowhub.request"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/api/v1/videos/feed")
    line = next(r for r in caplog.records if r.name == "knowhub.request")
    assert line.status == 200
    assert line.path == "/api/v1/videos/feed"
    assert line.duration_ms >= 0
