"""Make sure the configured Ollama models are pulled (local AI provider only).

AI is optional: if Ollama is unreachable this warns instead of failing, so the rest
of the app still comes up (uploads work without the writing assist).
"""

from __future__ import annotations

import os
import time

import httpx

STARTUP_WAIT_SECONDS = 30  # Ollama in docker may still be starting


def normalize(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


def fetch_tags(base_url: str) -> dict | None:
    deadline = time.monotonic() + STARTUP_WAIT_SECONDS
    while True:
        try:
            return httpx.get(f"{base_url}/api/tags", timeout=10).json()
        except httpx.HTTPError as exc:
            if time.monotonic() >= deadline:
                print(f"[provision] WARNING: Ollama not reachable at {base_url} ({exc}); AI unavailable")
                return None
            time.sleep(2)


def ensure_models(models: list[str]) -> None:
    base_url = (
        os.environ.get("LLM_API_BASE") or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
    ).rstrip("/")
    tags = fetch_tags(base_url)
    if tags is None:
        return

    installed = {normalize(m["name"]) for m in tags.get("models", [])}
    for model in models:
        if normalize(model) in installed:
            print(f"[provision] ai model {model}: present")
            continue
        print(f"[provision] ai model {model}: pulling (first time only, can take a few minutes)…")
        try:
            response = httpx.post(
                f"{base_url}/api/pull", json={"model": model, "stream": False}, timeout=None
            )
            response.raise_for_status()
            print(f"[provision] ai model {model}: pulled")
        except httpx.HTTPError as exc:
            print(f"[provision] WARNING: could not pull {model}: {exc}")
