"""Sign this machine in to Google Cloud again, from the web app.

For KnowHub running on someone's Mac with their own Google account (LOCAL_RUN.md). Every
so often Google makes that account sign in again; until it does, every BigQuery and
storage call fails. Instead of opening Terminal, the person running KnowHub clicks
"Reconnect Google Cloud" and signs in in their browser.

Both logins run here, on the machine the API runs on:

    gcloud auth login                       the gcloud command line (make setup-*, checks)
    gcloud auth application-default login   what the API itself uses

With BROWSER=true, gcloud "opens" the sign-in page with a command that does nothing, and
the page opens the printed URL itself: the API may have been started by cron, which
cannot open a browser window. Google redirects back to localhost:8085/8086, where gcloud
is listening, so this only works in a browser on the same machine; the API offers it only
to requests from there. The clients reload new credentials themselves
(core/gcp_credentials.py), so nothing needs restarting afterwards.

Not for a pod with a service account: there is no gcloud there and nothing to sign in.
GCLOUD_LOGIN_FROM_WEB=false turns it off.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field

from app.core.config import Settings

log = logging.getLogger("knowhub.gcloud")

STEPS = {
    "cli": ("Sign in to the gcloud command line", ["auth", "login"]),
    "adc": ("Allow KnowHub to use your Google account", ["auth", "application-default", "login"]),
}
LOGIN_TIMEOUT_S = 10 * 60  # gcloud waits for the browser forever; give up after this
CHECK_TIMEOUT_S = 20
CHECK_CACHE_S = 30
URL_RE = re.compile(r"https://accounts\.google\.com/\S+")


@dataclass
class Step:
    name: str
    label: str
    state: str = "starting"  # starting → waiting (URL known) → done | failed
    url: str | None = None
    error: str | None = None
    process: subprocess.Popen | None = field(default=None, repr=False)

    def public(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "state": self.state,
            "url": self.url,
            "error": self.error,
        }


_lock = threading.Lock()
_steps: dict[str, Step] = {}
_checked: tuple[float, dict] | None = None


# ------------------------------------------------------------------ who may use it
def gcloud_binary() -> str | None:
    # cron's PATH is short; knowhub.sh adds Homebrew's, this covers `make api` too
    return shutil.which("gcloud") or shutil.which("gcloud", path="/opt/homebrew/bin:/usr/local/bin")


def enabled(settings: Settings) -> bool:
    """Off on a service account (nothing to sign in) and wherever gcloud isn't installed."""
    return (
        settings.gcloud_login_from_web
        and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        and gcloud_binary() is not None
    )


def _loopback(address: str | None) -> bool:
    try:
        return address is not None and ipaddress.ip_address(address.strip()).is_loopback
    except ValueError:
        return address == "localhost"


def from_this_machine(client_host: str | None, forwarded_for: str | None) -> bool:
    """The browser runs on the machine the API runs on.

    The API listens on 127.0.0.1 only, so the web server's proxy is the direct client and
    X-Forwarded-For (which the proxy fills from the browser's address) says who is behind
    it. A browser can send its own X-Forwarded-For, so this decides who sees the button,
    not who is trusted: the worst a spoofer can do is start a sign-in that only someone at
    this machine can finish.
    """
    if not _loopback(client_host):
        return False
    return forwarded_for is None or all(_loopback(hop) for hop in forwarded_for.split(","))


# ------------------------------------------------------------------ are we signed in?
def _check_adc() -> dict:
    import google.auth
    import google.auth.transport.requests

    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())
    except Exception as exc:  # DefaultCredentialsError, RefreshError, TransportError
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    return {"ok": True}


def _gcloud(*args: str, timeout: float = CHECK_TIMEOUT_S) -> subprocess.CompletedProcess:
    return subprocess.run(
        [gcloud_binary() or "gcloud", *args, "--verbosity=error"],
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def _check_cli() -> dict:
    try:
        token = _gcloud("auth", "print-access-token")
        account = _gcloud("config", "get-value", "account").stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    if token.returncode != 0:
        return {"ok": False, "account": account or None, "error": token.stderr.strip()[-300:]}
    return {"ok": True, "account": account or None}


async def check(force: bool = False) -> dict:
    """{ok, cli, adc}. Cached for a little while: each check is a token refresh and two
    gcloud runs, and every open page asks."""
    global _checked
    if not force and _checked and time.monotonic() - _checked[0] < CHECK_CACHE_S:
        return _checked[1]
    cli, adc = await asyncio.gather(asyncio.to_thread(_check_cli), asyncio.to_thread(_check_adc))
    result = {"ok": cli["ok"] and adc["ok"], "cli": cli, "adc": adc}
    if not result["ok"]:
        log.warning(
            "Google Cloud sign-in needed: gcloud %s, application-default %s",
            "ok" if cli["ok"] else cli.get("error"),
            "ok" if adc["ok"] else adc.get("error"),
        )
    _checked = (time.monotonic(), result)
    return result


# ------------------------------------------------------------------ signing in
def running() -> bool:
    return any(step.state in ("starting", "waiting") for step in _steps.values())


def steps() -> list[dict]:
    return [step.public() for step in _steps.values()]


def start(settings: Settings) -> None:
    """Start both logins (they listen on different ports, so they run side by side).
    A second click while they're running changes nothing."""
    with _lock:
        if running():
            return
        _steps.clear()
        for name, (label, args) in STEPS.items():
            step = Step(name, label)
            _steps[name] = step
            threading.Thread(target=_run, args=(step, args, settings), daemon=True).start()
    log.info("Google Cloud sign-in started from the web app")


def _run(step: Step, args: list[str], settings: Settings) -> None:
    global _checked
    env = {**os.environ, "BROWSER": "true", "CLOUDSDK_CORE_DISABLE_PROMPTS": "1"}
    try:
        step.process = subprocess.Popen(
            [gcloud_binary() or "gcloud", *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
    except OSError as exc:
        step.state, step.error = "failed", f"could not run gcloud: {exc}"
        return

    timed_out = threading.Event()

    def give_up() -> None:
        timed_out.set()
        step.process.kill()

    timer = threading.Timer(LOGIN_TIMEOUT_S, give_up)
    timer.start()
    tail: list[str] = []
    assert step.process.stdout is not None
    for line in step.process.stdout:
        match = URL_RE.search(line)
        if match:
            if step.url is None:
                step.url, step.state = match.group(0), "waiting"
        elif "browser has been opened" not in line:
            tail = (tail + [line.strip()])[-5:]  # gcloud's own words, for a failure
    code = step.process.wait()
    timer.cancel()
    _checked = None  # the next check asks Google again (before "done", so no poll sees a stale ok)

    if code == 0:
        if step.name == "adc":
            _set_quota_project(settings)
        step.state = "done"
        log.info("Google Cloud sign-in: %s done", step.name)
    else:
        step.state = "failed"
        stopped = f"gcloud stopped (exit {code})"
        tail_text = " ".join(filter(None, tail))[-300:] or stopped
        step.error = "timed out waiting for the sign-in" if timed_out.is_set() else tail_text
        log.warning("Google Cloud sign-in: %s failed: %s", step.name, step.error)


def _set_quota_project(settings: Settings) -> None:
    """User credentials need a project to bill API calls to (LOCAL_RUN.md step 4)."""
    try:
        result = _gcloud(
            "auth", "application-default", "set-quota-project", settings.gcp_project_id, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("could not set the quota project: %s", exc)
        return
    if result.returncode != 0:
        log.warning("could not set the quota project: %s", result.stderr.strip()[-300:])
