"""Dependency checks behind GET /api/v1/health.

Required: database, storage, pubsub (the app can't work without them).
Optional: ai (uploads still work without the writing assist) → reported as degraded.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy import text

from app.adapters.ai import check_ai
from app.adapters.eventbus import get_event_bus
from app.adapters.storage import get_storage
from app.core.config import Settings
from app.core.db import get_engine

CHECK_TIMEOUT_SECONDS = 8
REQUIRED = ("database", "storage", "pubsub")


MIGRATIONS_SQL = text("SELECT max(version), count(*) FROM schema_migrations")
EXTENSIONS_SQL = text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')")


async def check_database(settings: Settings) -> dict:
    async with get_engine().connect() as conn:
        latest = (await conn.execute(MIGRATIONS_SQL)).one()
        extensions = (await conn.execute(EXTENSIONS_SQL)).scalars().all()
    return {
        "ok": latest[1] > 0,
        "migrations_applied": latest[1],
        "latest_migration": latest[0],
        "extensions": sorted(extensions),
    }


async def check_storage(settings: Settings) -> dict:
    missing = await asyncio.to_thread(get_storage().missing_buckets, settings.buckets)
    return {"ok": not missing, "buckets": settings.buckets, "missing": missing}


async def check_pubsub(settings: Settings) -> dict:
    missing = await asyncio.to_thread(get_event_bus().missing_topics, settings.pubsub_topics)
    return {"ok": not missing, "topics": len(settings.pubsub_topics), "missing": missing}


CHECKS: dict[str, Callable[[Settings], Awaitable[dict]]] = {
    "database": check_database,
    "storage": check_storage,
    "pubsub": check_pubsub,
    "ai": check_ai,
}


async def _run(check: Callable[[Settings], Awaitable[dict]], settings: Settings) -> dict:
    try:
        return await asyncio.wait_for(check(settings), CHECK_TIMEOUT_SECONDS)
    except TimeoutError:
        return {"ok": False, "error": f"timed out after {CHECK_TIMEOUT_SECONDS}s"}
    except Exception as exc:  # report, don't crash the health endpoint
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


async def run_checks(settings: Settings) -> tuple[str, dict[str, dict]]:
    names = list(CHECKS)
    results = await asyncio.gather(*(_run(CHECKS[n], settings) for n in names))
    checks = dict(zip(names, results, strict=True))
    if not all(checks[n]["ok"] for n in REQUIRED):
        status = "down"
    elif not all(c["ok"] for c in checks.values()):
        status = "degraded"
    else:
        status = "ok"
    return status, checks
