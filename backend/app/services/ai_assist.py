"""The "Improve with AI" writing assist used on the upload form.

The model only ever rewrites what the author typed: prompts forbid inventing facts,
and nothing is saved until the author accepts the suggestion.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import ai
from app.core.config import Settings
from app.models.ai import AIRequest

PROMPT_DIR = Path(__file__).resolve().parent.parent / "ai" / "prompts"
FIELDS = ("title", "description", "tags", "comment")
MAX_TITLE_CHARS = 200
HEADINGS = ("problem", "root cause", "fix", "takeaways")
MAX_PER_MINUTE = 10


log = logging.getLogger("knowhub.ai")


class AssistError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@lru_cache
def load_prompt(field: str) -> str:
    path = PROMPT_DIR / f"{field}.md"
    if not path.is_file():
        raise AssistError(f"No prompt for '{field}'", status_code=500)
    return path.read_text(encoding="utf-8").strip()


def build_prompt(field: str, text: str, context: dict[str, str | None]) -> str:
    """The author's text, plus whatever else they have filled in so far."""
    lines = []
    for label, key in (("Title", "title"), ("Topic", "topic"), ("Category", "category"), ("Type", "type")):
        value = (context.get(key) or "").strip()
        if value and not (field == "title" and key == "title"):
            lines.append(f"{label}: {value}")
    context_block = "\n".join(lines)
    header = f"Context (for reference only, do not repeat it):\n{context_block}\n\n" if context_block else ""
    label = {
        "title": "title",
        "description": "description",
        "tags": "title and description",
        "comment": "comment",
    }[field]
    return f'{header}The author\'s {label}:\n"""\n{text.strip()}\n"""'


def clean(field: str, output: str) -> str:
    """Small models like to add preamble and quotes; strip that before showing it."""
    text = output.strip()
    text = re.sub(r"^(here('s| is)[^:\n]*:|sure[^:\n]*:|revised[^:\n]*:)\s*", "", text, flags=re.I)
    text = re.sub(r"^```[a-z]*\n?|```$", "", text.strip(), flags=re.M).strip()
    if field in ("title", "tags"):
        text = text.splitlines()[0].strip() if text else text
    if text[:1] in {'"', "'"} and text[-1:] == text[:1]:
        text = text[1:-1].strip()
    if field == "title":
        text = text.rstrip(".").strip()[:MAX_TITLE_CHARS]
    if field == "description":
        text = drop_preamble(text)
    return text


def drop_preamble(text: str) -> str:
    """Small models like to open with a summary line before the first heading, which
    just repeats what follows. If headings are used, start at the first one."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().rstrip(":-").strip().lower() in HEADINGS:
            return "\n".join(lines[index:]).strip()
    return text


def parse_tags(output: str) -> list[str]:
    raw = re.split(r"[,\n]", output)
    tags = []
    for item in raw:
        tag = re.sub(r"[^a-z0-9-]+", "-", item.strip().lower()).strip("-")
        if 2 <= len(tag) <= 40 and tag not in tags:
            tags.append(tag)
    return tags[:6]


async def check_rate_limit(session: AsyncSession, user_id: uuid.UUID) -> None:
    since = datetime.now(UTC) - timedelta(minutes=1)
    used = await session.scalar(
        select(func.count())
        .select_from(AIRequest)
        .where(AIRequest.user_id == user_id, AIRequest.created_at >= since)
    )
    if (used or 0) >= MAX_PER_MINUTE:
        raise AssistError("You're going a bit fast. Try again in a minute.", status_code=429)


async def enhance(
    session: AsyncSession,
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

    await check_rate_limit(session, user_id)

    started = datetime.now(UTC)
    record = AIRequest(
        user_id=user_id,
        field=field,
        provider=settings.provider,
        model=settings.ai_model,
        input_chars=len(text),
        created_at=started,
    )
    try:
        output = await ai.generate_text(
            settings, system=load_prompt(field), prompt=build_prompt(field, text, context)
        )
    except ai.AIUnavailable as exc:
        log.warning("ai %s failed on %s/%s: %s", field, settings.provider, settings.ai_model, exc)
        record.error = str(exc)[:500]
        session.add(record)
        await session.commit()
        raise AssistError(str(exc), status_code=503) from exc

    suggestion = clean(field, output)
    log.info(
        "ai %s: %s/%s rewrote %d chars into %d in %dms",
        field,
        settings.provider,
        settings.ai_model,
        len(text),
        len(suggestion),
        int((datetime.now(UTC) - started).total_seconds() * 1000),
    )
    record.output_chars = len(suggestion)
    record.latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    session.add(record)
    await session.commit()

    result = {
        "field": field,
        "suggestion": suggestion,
        "request_id": str(record.id),
        # shown in the suggestion box, so the author knows what wrote it
        "provider": settings.provider,
        "model": settings.ai_model,
    }
    if field == "tags":
        result["items"] = parse_tags(suggestion)
    return result


async def record_outcome(session: AsyncSession, request_id: uuid.UUID, accepted: bool) -> None:
    """Did the author keep the suggestion? Tells us whether the prompts are any good."""
    record = await session.get(AIRequest, request_id)
    if record is not None:
        record.accepted = accepted
        await session.commit()
