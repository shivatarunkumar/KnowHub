"""The "Improve with AI" writing assist, on BigQuery.

Prompting, cleaning and the provider call are shared with app/services/ai_assist.py;
only the rate limit and the ai_requests log are stored differently.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.adapters import ai
from app.core.config import Settings
from app.services.ai_assist import (
    FIELDS,
    MAX_PER_MINUTE,
    AssistError,
    build_prompt,
    clean,
    load_prompt,
    parse_tags,
)
from app_bq.core.bq import BigQueryDB

__all__ = ["AssistError", "enhance"]

log = logging.getLogger("knowhub.ai")


async def check_rate_limit(db: BigQueryDB, user_id: uuid.UUID) -> None:
    used = await db.scalar(
        "SELECT COUNT(*) FROM {ai_requests} WHERE user_id = @user_id AND created_at >= @since",
        user_id=user_id,
        since=datetime.now(UTC) - timedelta(minutes=1),
    )
    if (used or 0) >= MAX_PER_MINUTE:
        raise AssistError("You're going a bit fast. Try again in a minute.", status_code=429)


async def enhance(
    db: BigQueryDB,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    field: str,
    text: str,
    context: dict[str, str | None],
) -> dict:
    if field not in FIELDS:
        raise AssistError(f"Can't improve '{field}'")
    text = (text or "").strip()
    if len(text) < 3:
        raise AssistError("Write a few words first, then let the AI tidy them up.")
    if len(text) > settings.ai_enhance_max_chars:
        raise AssistError(f"That's longer than the {settings.ai_enhance_max_chars} character limit.")

    await check_rate_limit(db, user_id)

    started = datetime.now(UTC)
    record = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "field": field,
        "provider": settings.provider,
        "model": settings.ai_model,
        "input_chars": len(text),
        "output_chars": 0,
        "created_at": started,
    }
    try:
        output = await ai.generate_text(
            settings, system=load_prompt(field), prompt=build_prompt(field, text, context)
        )
    except ai.AIUnavailable as exc:
        log.warning("ai %s failed on %s/%s: %s", field, settings.provider, settings.ai_model, exc)
        await db.insert("ai_requests", {**record, "error": str(exc)[:500]})
        raise AssistError(str(exc), status_code=503) from exc

    suggestion = clean(field, output)
    latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    log.info(
        "ai %s: %s/%s rewrote %d chars into %d in %dms",
        field,
        settings.provider,
        settings.ai_model,
        len(text),
        len(suggestion),
        latency_ms,
    )
    await db.insert("ai_requests", {**record, "output_chars": len(suggestion), "latency_ms": latency_ms})

    result = {
        "field": field,
        "suggestion": suggestion,
        "request_id": str(record["id"]),
        "provider": settings.provider,
        "model": settings.ai_model,
    }
    if field == "tags":
        result["items"] = parse_tags(suggestion)
    return result
