"""Google clients that pick up a new `gcloud auth application-default login` by themselves.

A Google client reads Application Default Credentials once, when it is built, and keeps
the refresh token in memory. When that token dies (Workspace reauth, a revoked session),
signing in again rewrites the credentials file, but a long-running API would go on
using the dead token until it was restarted.

@per_login caches like @lru_cache, and builds again whenever the credentials file has
changed since, so signing in again is enough.
"""

from __future__ import annotations

import functools
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("knowhub.gcp")


def adc_path() -> Path:
    """The file google.auth.default() reads: GOOGLE_APPLICATION_CREDENTIALS, else gcloud's."""
    explicit = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if explicit:
        return Path(explicit)
    config = os.environ.get("CLOUDSDK_CONFIG") or Path.home() / ".config" / "gcloud"
    return Path(config) / "application_default_credentials.json"


def credentials_stamp() -> int | None:
    """Changes whenever the credentials file is rewritten; None when there is none."""
    try:
        return adc_path().stat().st_mtime_ns
    except OSError:
        return None


def per_login[T](build: Callable[[], T]) -> Callable[[], T]:
    """Cache build()'s result until the credentials file changes."""
    lock = threading.Lock()
    cached: dict[str, object] = {}

    @functools.wraps(build)
    def get() -> T:
        stamp = credentials_stamp()
        with lock:
            if "value" not in cached or cached["stamp"] != stamp:
                if "value" in cached:
                    log.info("Google credentials changed: rebuilding %s", build.__name__)
                cached["value"] = build()
                cached["stamp"] = stamp
            return cached["value"]  # type: ignore[return-value]

    def cache_clear() -> None:
        with lock:
            cached.clear()

    get.cache_clear = cache_clear  # type: ignore[attr-defined]
    return get
