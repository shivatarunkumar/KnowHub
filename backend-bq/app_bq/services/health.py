"""Dependency checks behind GET /api/v1/health when RUN_ON=BQ.

Storage, Pub/Sub and AI are checked exactly as for Postgres (the same functions); the
database check asks BigQuery instead: does the dataset exist, does it have every table
in infra/gcs/bq/tables, and are the topics seeded.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import Settings
from app.services import health as shared
from app_bq.core.bq import get_db, schema

log = logging.getLogger("knowhub.health")


async def check_database(settings: Settings) -> dict:
    db = get_db()
    expected = set(schema())
    tables = await asyncio.to_thread(
        lambda: {t.table_id for t in db.client.list_tables(f"{db.project}.{db.dataset}")}
    )
    missing = sorted(expected - tables)
    topics = await db.scalar("SELECT COUNT(*) FROM {topics}") if "topics" in tables else 0
    return {
        "ok": not missing and topics > 0,
        "backend": "bigquery",
        "dataset": f"{db.project}.{db.dataset}",
        "location": db.location,
        "tables": len(expected & tables),
        "missing": missing,
        "topics": topics,
        **({"fix": "make setup-bq"} if missing or not topics else {}),
    }


async def run_checks(settings: Settings) -> tuple[str, dict[str, dict]]:
    checks = {**shared.CHECKS, "database": check_database}
    names = list(checks)
    results = await asyncio.gather(*(shared._run(n, checks[n], settings) for n in names))
    results_by_name = dict(zip(names, results, strict=True))
    if not all(results_by_name[n]["ok"] for n in shared.REQUIRED):
        status = "down"
    elif not all(c["ok"] for c in results_by_name.values()):
        status = "degraded"
    else:
        status = "ok"
    return status, results_by_name
