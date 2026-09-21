"""AI provider adapter.

One switch, `PROVIDER`, chooses where the writing assist runs:

    openai      any OpenAI-compatible endpoint (OpenAI itself, or a gateway — set
                LLM_API_BASE to point at Ollama, vLLM, LiteLLM, a company proxy)
    anthropic   the Anthropic Messages API
    gemini      Google AI Studio (API key)
    vertex      Vertex AI on GCP (Application Default Credentials, no key)
    ollama      Ollama's own API on LLM_API_BASE
    none        the assist is switched off

Every provider is called over plain HTTP with httpx, so no provider SDK is a dependency.
MODEL and LLM_API_BASE override the per-provider defaults in config.py.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

import httpx

from app.core.config import Settings

VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
ANTHROPIC_VERSION = "2023-06-01"
# faithful rewriting, not creative writing
TEMPERATURE = 0.1
TOP_P = 0.8
MAX_OUTPUT_TOKENS = 700


class AIUnavailable(Exception):
    """The provider is unreachable, slow or misconfigured. Callers carry on without AI."""


def _client(base_url: str = "", timeout: float = 30.0) -> httpx.AsyncClient:
    """Indirection so tests can hand in a mock transport."""
    return httpx.AsyncClient(base_url=base_url, timeout=timeout)


def _normalize(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


def _versioned(base: str, version: str) -> str:
    """Join a base URL with an API version without doubling it: someone who sets
    LLM_API_BASE=https://api.openai.com/v1 means the same as .../ without it."""
    base = base.rstrip("/")
    return base if base.endswith(f"/{version}") else f"{base}/{version}"


# ------------------------------------------------------------------ errors
def _http_failure(response: httpx.Response, settings: Settings, what: str) -> AIUnavailable:
    """Turn a provider's error into something the person running KnowHub can act on."""
    body = response.text
    status = response.status_code
    detail = body[:300]

    if status in (401, 403):
        # Vertex says "the API is off" and "you lack permission" with the same status,
        # and puts the reason deep in error.details[], past any truncation.
        if "SERVICE_DISABLED" in body:
            return AIUnavailable(
                "The Vertex AI API is not enabled on this project. Enable it with: "
                f"gcloud services enable aiplatform.googleapis.com --project {settings.gcp_project_id}"
            )
        if settings.provider == "vertex":
            return AIUnavailable(
                "Vertex AI refused these credentials. Run 'gcloud auth application-default login' "
                f"and give the account roles/aiplatform.user on {settings.gcp_project_id}"
            )
        key = settings.ai_key_setting
        if key and not settings.ai_api_key:
            return AIUnavailable(f"{what} needs an API key: set {key} in .env")
        return AIUnavailable(f"{what} rejected the API key in {key or 'this configuration'}")

    if status == 404:
        return AIUnavailable(
            f"{what} has no model '{settings.ai_model}'. Check MODEL in .env"
            + (f" (base URL: {settings.ai_base_url})" if settings.llm_api_base else "")
        )
    if status == 429:
        return AIUnavailable(f"{what} is rate limiting this account; try again shortly")
    if status >= 500:
        return AIUnavailable(f"{what} is having trouble ({status}); try again shortly")
    return AIUnavailable(f"{what} request failed ({status}): {detail}")


async def _post(
    settings: Settings, url: str, payload: dict, headers: dict, timeout: float, what: str
) -> dict:
    try:
        async with _client(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise AIUnavailable(f"{what} took too long to respond") from exc
    except httpx.HTTPError as exc:
        raise AIUnavailable(f"Can't reach {what} at {settings.ai_base_url or 'its endpoint'}: {exc}") from exc
    if response.status_code >= 400:
        raise _http_failure(response, settings, what)
    return response.json()


async def _get(settings: Settings, url: str, headers: dict, timeout: float, what: str) -> dict:
    try:
        async with _client(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise AIUnavailable(f"Can't reach {what} at {settings.ai_base_url or 'its endpoint'}: {exc}") from exc
    if response.status_code >= 400:
        raise _http_failure(response, settings, what)
    return response.json()


# ------------------------------------------------------------------ openai-compatible
def _openai_headers(settings: Settings) -> dict:
    headers = {"content-type": "application/json"}
    # a gateway on LLM_API_BASE (Ollama, vLLM) usually needs no key
    if settings.ai_api_key:
        headers["Authorization"] = f"Bearer {settings.ai_api_key}"
    return headers


# OpenAI's reasoning models fix temperature at 1 and renamed the output-length setting.
OPENAI_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


async def _openai_generate(settings: Settings, *, system: str, prompt: str, timeout: float) -> str:
    payload: dict = {
        "model": settings.ai_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    }
    if settings.ai_model.startswith(OPENAI_REASONING_PREFIXES):
        payload["max_completion_tokens"] = MAX_OUTPUT_TOKENS
    else:
        payload["temperature"] = TEMPERATURE
        payload["top_p"] = TOP_P
        payload["max_tokens"] = MAX_OUTPUT_TOKENS
    body = await _post(
        settings,
        f"{_versioned(settings.ai_base_url, 'v1')}/chat/completions",
        payload,
        _openai_headers(settings),
        timeout,
        "OpenAI",
    )
    choices = body.get("choices") or []
    if not choices:
        raise AIUnavailable("OpenAI returned no choices")
    text = ((choices[0].get("message") or {}).get("content") or "").strip()
    if text:
        return text
    if choices[0].get("finish_reason") == "length":
        raise AIUnavailable("OpenAI hit the output limit before writing anything")
    raise AIUnavailable("OpenAI returned an empty response")


async def _openai_check(settings: Settings) -> dict:
    await _get(
        settings,
        f"{_versioned(settings.ai_base_url, 'v1')}/models",
        _openai_headers(settings),
        10.0,
        "OpenAI",
    )
    return {
        "ok": True,
        "provider": settings.provider,
        "model": settings.ai_model,
        "base": settings.ai_base_url,
    }


# ------------------------------------------------------------------ anthropic
async def _anthropic_generate(settings: Settings, *, system: str, prompt: str, timeout: float) -> str:
    # No temperature: the current Claude models reject it outright ("`temperature` is
    # deprecated for this model"), and faithfulness here comes from the prompt, not from
    # sampling settings.
    payload = {
        "model": settings.ai_model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": settings.ai_api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = await _post(
        settings, f"{_versioned(settings.ai_base_url, 'v1')}/messages", payload, headers, timeout, "Anthropic"
    )
    text = "".join(
        block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"
    ).strip()
    if text:
        return text
    if body.get("stop_reason") == "max_tokens":
        raise AIUnavailable("Anthropic hit the output limit before writing anything")
    raise AIUnavailable("Anthropic returned an empty response")


async def _anthropic_check(settings: Settings) -> dict:
    headers = {"x-api-key": settings.ai_api_key, "anthropic-version": ANTHROPIC_VERSION}
    await _get(settings, f"{_versioned(settings.ai_base_url, 'v1')}/models", headers, 10.0, "Anthropic")
    return {"ok": True, "provider": "anthropic", "model": settings.ai_model, "base": settings.ai_base_url}


# ------------------------------------------------------------------ gemini (shared shape)
def _gemini_payload(system: str, prompt: str) -> dict:
    return {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {
            "temperature": TEMPERATURE,
            "topP": TOP_P,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }


def _gemini_text(body: dict, what: str) -> str:
    """Pull the reply out, and explain the empty ones rather than returning nothing."""
    blocked = (body.get("promptFeedback") or {}).get("blockReason")
    if blocked:
        raise AIUnavailable(f"{what} declined to answer ({blocked})")
    candidates = body.get("candidates") or []
    if not candidates:
        raise AIUnavailable(f"{what} returned no candidates")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if text:
        return text
    reason = candidate.get("finishReason", "unknown")
    if reason == "MAX_TOKENS":
        raise AIUnavailable(f"{what} hit the output limit before writing anything")
    raise AIUnavailable(f"{what} returned an empty response ({reason})")


# --- google ai studio
def _studio_url(settings: Settings, method: str) -> str:
    return f"{_versioned(settings.ai_base_url, 'v1beta')}/models/{settings.ai_model}:{method}"


def _studio_headers(settings: Settings) -> dict:
    # the key goes in a header rather than the query string, so it stays out of logs
    return {"x-goog-api-key": settings.ai_api_key, "content-type": "application/json"}


async def _gemini_generate(settings: Settings, *, system: str, prompt: str, timeout: float) -> str:
    body = await _post(
        settings,
        _studio_url(settings, "generateContent"),
        _gemini_payload(system, prompt),
        _studio_headers(settings),
        timeout,
        "Gemini",
    )
    return _gemini_text(body, "Gemini")


async def _gemini_check(settings: Settings) -> dict:
    await _get(
        settings,
        f"{_versioned(settings.ai_base_url, 'v1beta')}/models",
        _studio_headers(settings),
        10.0,
        "Gemini",
    )
    return {"ok": True, "provider": "gemini", "model": settings.ai_model, "base": settings.ai_base_url}


# --- vertex ai (same request shape, ADC instead of a key)
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


def _vertex_url(settings: Settings, method: str) -> str:
    location = settings.ai_location
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    return (
        f"https://{host}/v1/projects/{settings.gcp_project_id}"
        f"/locations/{location}/publishers/google/models/{settings.ai_model}:{method}"
    )


async def _vertex_headers(settings: Settings) -> dict:
    return {
        "Authorization": f"Bearer {await _access_token()}",
        # bills and attributes the call to this project, which user credentials need
        "x-goog-user-project": settings.gcp_project_id,
        "content-type": "application/json",
    }


async def _vertex_generate(settings: Settings, *, system: str, prompt: str, timeout: float) -> str:
    if not settings.gcp_project_id:
        raise AIUnavailable("GCP_PROJECT_ID is not set, so Vertex AI has no project to call")
    body = await _post(
        settings,
        _vertex_url(settings, "generateContent"),
        _gemini_payload(system, prompt),
        await _vertex_headers(settings),
        timeout,
        "Vertex AI",
    )
    return _gemini_text(body, "Vertex AI")


async def _vertex_check(settings: Settings) -> dict:
    """countTokens costs nothing and still proves credentials, the API and the model."""
    if not settings.gcp_project_id:
        return {"ok": False, "provider": "vertex", "error": "GCP_PROJECT_ID is not set"}
    payload = {"contents": [{"role": "user", "parts": [{"text": "ping"}]}]}
    await _post(
        settings,
        _vertex_url(settings, "countTokens"),
        payload,
        await _vertex_headers(settings),
        10.0,
        "Vertex AI",
    )
    return {
        "ok": True,
        "provider": "vertex",
        "model": settings.ai_model,
        "location": settings.ai_location,
        "project": settings.gcp_project_id,
    }


# ------------------------------------------------------------------ ollama
async def _ollama_generate(settings: Settings, *, system: str, prompt: str, timeout: float) -> str:
    payload = {
        "model": settings.ai_model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": TEMPERATURE, "top_p": TOP_P, "num_predict": MAX_OUTPUT_TOKENS},
    }
    body = await _post(
        settings,
        f"{settings.ai_base_url}/api/generate",
        payload,
        {"content-type": "application/json"},
        timeout,
        "Ollama",
    )
    text = (body.get("response") or "").strip()
    if not text:
        raise AIUnavailable("Ollama returned an empty response")
    return text


async def _ollama_check(settings: Settings) -> dict:
    body = await _get(settings, f"{settings.ai_base_url}/api/tags", {}, 5.0, "Ollama")
    installed = {_normalize(m["name"]) for m in body.get("models", [])}
    wanted = [settings.ai_model, settings.ai_embedding_model]
    missing = [m for m in wanted if _normalize(m) not in installed]
    return {"ok": not missing, "provider": "ollama", "models": wanted, "missing_models": missing}


# ------------------------------------------------------------------ public
GENERATORS = {
    "openai": _openai_generate,
    "anthropic": _anthropic_generate,
    "gemini": _gemini_generate,
    "vertex": _vertex_generate,
    "ollama": _ollama_generate,
}

CHECKS = {
    "openai": _openai_check,
    "anthropic": _anthropic_check,
    "gemini": _gemini_check,
    "vertex": _vertex_check,
    "ollama": _ollama_check,
}


async def check_ai(settings: Settings) -> dict:
    """Return {"ok": bool, "provider": ..., ...}. AI is optional, so callers treat
    a failure as degraded, not down."""
    if settings.provider == "none":
        return {"ok": True, "provider": "none", "detail": "AI disabled"}
    try:
        return await CHECKS[settings.provider](settings)
    except AIUnavailable as exc:
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.ai_model,
            "error": str(exc),
        }


async def generate_text(
    settings: Settings, *, system: str, prompt: str, timeout_seconds: float = 90.0
) -> str:
    """One-shot completion. Raises AIUnavailable rather than failing the caller's request."""
    if settings.provider == "none":
        raise AIUnavailable("AI is switched off (PROVIDER=none)")
    return await GENERATORS[settings.provider](
        settings, system=system, prompt=prompt, timeout=timeout_seconds
    )
