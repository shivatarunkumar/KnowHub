"""AI provider adapter: Ollama on a laptop, Vertex AI (Gemini) in the cloud.

Both providers are reached over plain HTTP with httpx, and Vertex is authenticated with
Application Default Credentials — the same credentials the storage and Pub/Sub adapters
use, so switching is a config change (AI_PROVIDER) and nothing else.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

import httpx

from app.core.config import Settings

VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
# faithful rewriting, not creative writing
GENERATION = {"temperature": 0.1, "top_p": 0.8, "max_tokens": 700}


def _normalize(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


class AIUnavailable(Exception):
    """The provider is unreachable, slow or misconfigured. Callers carry on without AI."""


def _client(base_url: str = "", timeout: float = 30.0) -> httpx.AsyncClient:
    """Indirection so tests can hand in a mock transport."""
    return httpx.AsyncClient(base_url=base_url, timeout=timeout)


# ------------------------------------------------------------------ vertex ai
@lru_cache(maxsize=1)
def _credentials():
    """ADC, loaded once. Cached because google.auth.default() touches the filesystem."""
    import google.auth

    credentials, _ = google.auth.default(scopes=[VERTEX_SCOPE])
    return credentials


async def _access_token() -> str:
    import google.auth.transport.requests

    credentials = _credentials()
    if not credentials.valid:
        # blocking refresh: off the event loop
        await asyncio.to_thread(credentials.refresh, google.auth.transport.requests.Request())
    return credentials.token


def _endpoint(settings: Settings, model: str, method: str) -> str:
    location = settings.ai_location
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    return (
        f"https://{host}/v1/projects/{settings.gcp_project_id}"
        f"/locations/{location}/publishers/google/models/{model}:{method}"
    )


def _vertex_failure(response: httpx.Response, settings: Settings) -> AIUnavailable:
    """Turn a Vertex error into something the person running KnowHub can act on."""
    body = response.text
    detail = body[:300]
    status = response.status_code
    # "the API is off" and "you lack permission" are both 403 and need different fixes.
    # The reason sits in error.details[], well past any truncation, so search the whole body.
    if status == 403 and "SERVICE_DISABLED" in body:
        return AIUnavailable(
            "The Vertex AI API is not enabled on this project. Enable it with: "
            f"gcloud services enable aiplatform.googleapis.com --project {settings.gcp_project_id}"
        )
    if status in (401, 403):
        return AIUnavailable(
            "Vertex AI refused these credentials. Run 'gcloud auth application-default login' and "
            f"make sure the account has roles/aiplatform.user on {settings.gcp_project_id}"
        )
    if status == 404:
        return AIUnavailable(
            f"Vertex AI has no model '{settings.ai_text_model}' in {settings.ai_location}. "
            "Check AI_TEXT_MODEL and VERTEX_LOCATION"
        )
    if status == 429:
        return AIUnavailable("Vertex AI is rate limiting this project; try again shortly")
    return AIUnavailable(f"Vertex AI request failed ({status}): {detail}")


async def _vertex_post(settings: Settings, method: str, payload: dict, timeout: float) -> dict:
    headers = {
        "Authorization": f"Bearer {await _access_token()}",
        # bills and attributes the call to this project, which user credentials need
        "x-goog-user-project": settings.gcp_project_id,
        "content-type": "application/json",
    }
    try:
        async with _client(timeout=timeout) as client:
            response = await client.post(
                _endpoint(settings, settings.ai_text_model, method), json=payload, headers=headers
            )
    except httpx.TimeoutException as exc:
        raise AIUnavailable("Vertex AI took too long to respond") from exc
    except httpx.HTTPError as exc:
        raise AIUnavailable(f"Can't reach Vertex AI: {exc}") from exc

    if response.status_code >= 400:
        raise _vertex_failure(response, settings)
    return response.json()


def _vertex_text(body: dict) -> str:
    """Pull the reply out, and explain the empty ones rather than returning nothing."""
    blocked = (body.get("promptFeedback") or {}).get("blockReason")
    if blocked:
        raise AIUnavailable(f"Vertex AI declined to answer ({blocked})")

    candidates = body.get("candidates") or []
    if not candidates:
        raise AIUnavailable("Vertex AI returned no candidates")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if text:
        return text
    reason = candidate.get("finishReason", "unknown")
    if reason == "MAX_TOKENS":
        raise AIUnavailable("Vertex AI hit the output limit before writing anything")
    raise AIUnavailable(f"Vertex AI returned an empty response ({reason})")


async def _vertex_generate(settings: Settings, *, system: str, prompt: str, timeout: float) -> str:
    if not settings.gcp_project_id:
        raise AIUnavailable("GCP_PROJECT_ID is not set, so Vertex AI has no project to call")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {
            "temperature": GENERATION["temperature"],
            "topP": GENERATION["top_p"],
            "maxOutputTokens": GENERATION["max_tokens"],
        },
    }
    return _vertex_text(await _vertex_post(settings, "generateContent", payload, timeout))


async def _vertex_check(settings: Settings) -> dict:
    """countTokens costs nothing and still proves credentials, the API and the model."""
    if not settings.gcp_project_id:
        return {"ok": False, "provider": "vertex", "error": "GCP_PROJECT_ID is not set"}
    payload = {"contents": [{"role": "user", "parts": [{"text": "ping"}]}]}
    try:
        await _vertex_post(settings, "countTokens", payload, timeout=10.0)
    except AIUnavailable as exc:
        return {
            "ok": False,
            "provider": "vertex",
            "model": settings.ai_text_model,
            "location": settings.ai_location,
            "error": str(exc),
        }
    return {
        "ok": True,
        "provider": "vertex",
        "model": settings.ai_text_model,
        "location": settings.ai_location,
        "project": settings.gcp_project_id,
    }


# ------------------------------------------------------------------ ollama
async def _ollama_check(settings: Settings) -> dict:
    async with _client(base_url=settings.ollama_base_url, timeout=5) as client:
        response = await client.get("/api/tags")
        response.raise_for_status()
    installed = {_normalize(m["name"]) for m in response.json().get("models", [])}
    wanted = [settings.ai_text_model, settings.ai_embedding_model]
    missing = [m for m in wanted if _normalize(m) not in installed]
    return {"ok": not missing, "provider": "ollama", "models": wanted, "missing_models": missing}


async def _ollama_generate(settings: Settings, *, system: str, prompt: str, timeout: float) -> str:
    payload = {
        "model": settings.ai_text_model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": GENERATION["temperature"],
            "top_p": GENERATION["top_p"],
            "num_predict": GENERATION["max_tokens"],
        },
    }
    try:
        async with _client(base_url=settings.ollama_base_url, timeout=timeout) as client:
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


# ------------------------------------------------------------------ public
async def check_ai(settings: Settings) -> dict:
    """Return {"ok": bool, "provider": ..., ...}. AI is optional, so callers treat
    a failure as degraded, not down."""
    if settings.ai_provider == "none":
        return {"ok": True, "provider": "none", "detail": "AI disabled"}
    if settings.ai_provider == "vertex":
        return await _vertex_check(settings)
    return await _ollama_check(settings)


async def generate_text(
    settings: Settings, *, system: str, prompt: str, timeout_seconds: float = 90.0
) -> str:
    """One-shot completion. Raises AIUnavailable rather than failing the caller's request."""
    if settings.ai_provider == "none":
        raise AIUnavailable("AI is switched off (AI_PROVIDER=none)")
    if settings.ai_provider == "vertex":
        return await _vertex_generate(settings, system=system, prompt=prompt, timeout=timeout_seconds)
    return await _ollama_generate(settings, system=system, prompt=prompt, timeout=timeout_seconds)
