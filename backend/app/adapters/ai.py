"""AI provider adapter: Ollama locally, Vertex AI on GCP (Phase 10)."""

from __future__ import annotations

import httpx

from app.core.config import Settings


def _normalize(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


class AIUnavailable(Exception):
    """The provider is unreachable, slow or misconfigured. Callers carry on without AI."""


async def check_ai(settings: Settings) -> dict:
    """Return {"ok": bool, "provider": ..., ...}. AI is optional, so callers treat
    a failure as degraded, not down."""
    if settings.ai_provider == "none":
        return {"ok": True, "provider": "none", "detail": "AI disabled"}
    if settings.ai_provider == "vertex":
        return {"ok": False, "provider": "vertex", "detail": "Vertex AI provider arrives in Phase 10"}

    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=5) as client:
        response = await client.get("/api/tags")
        response.raise_for_status()
    installed = {_normalize(m["name"]) for m in response.json().get("models", [])}
    wanted = [settings.ai_text_model, settings.ai_embedding_model]
    missing = [m for m in wanted if _normalize(m) not in installed]
    return {"ok": not missing, "provider": "ollama", "models": wanted, "missing_models": missing}


async def generate_text(
    settings: Settings, *, system: str, prompt: str, timeout_seconds: float = 90.0
) -> str:
    """One-shot completion. Raises AIUnavailable rather than failing the caller's request."""
    if settings.ai_provider == "none":
        raise AIUnavailable("AI is switched off (AI_PROVIDER=none)")
    if settings.ai_provider == "vertex":
        raise AIUnavailable("The Vertex AI provider arrives in Phase 10")

    payload = {
        "model": settings.ai_text_model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        # low temperature: we want faithful rewriting, not creative writing
        # near-zero temperature: this is copy editing, not creative writing
        "options": {"temperature": 0.1, "top_p": 0.8, "num_predict": 700},
    }
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=timeout_seconds) as client:
            response = await client.post("/api/generate", json=payload)
            response.raise_for_status()
            body = response.json()
    except httpx.TimeoutException as exc:
        raise AIUnavailable("The AI model took too long to respond") from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:200]
        if exc.response.status_code == 404:
            raise AIUnavailable(f"Model '{settings.ai_text_model}' is not installed") from exc
        raise AIUnavailable(f"AI request failed: {detail}") from exc
    except httpx.HTTPError as exc:
        raise AIUnavailable(f"Can't reach the AI service at {settings.ollama_base_url}") from exc

    text = (body.get("response") or "").strip()
    if not text:
        raise AIUnavailable("The AI model returned an empty response")
    return text
