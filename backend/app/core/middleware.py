"""One log line per request, and a request id that ties everything else to it.

Written as raw ASGI rather than BaseHTTPMiddleware on purpose: BaseHTTPMiddleware runs the
endpoint in its own task, so a contextvar the auth dependency sets (which user this is)
is invisible by the time the middleware logs. Plain ASGI shares the context, so the
request line can name the person who made it.
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import Timer, new_request_id, request_id_var, user_var

log = logging.getLogger("knowhub.request")

# Health polling would otherwise be most of the log; its failures are logged elsewhere.
QUIET_PATHS = {"/api/v1/health", "/healthz"}


class RequestLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.decode(): value.decode() for key, value in scope.get("headers", [])}
        # honour an id from upstream (a proxy, another service) so one trace spans both
        request_id = headers.get("x-request-id") or new_request_id()
        request_id_var.set(request_id)
        user_var.set("")
        timer = Timer()

        method = scope.get("method", "?")
        path = scope.get("path", "")
        raw_query = scope.get("query_string", b"").decode()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            # the handler blew up: log it here, with the request id, before it becomes a 500
            log.exception("%s %s failed after %dms", method, path, timer.ms)
            raise

        if path in QUIET_PATHS and status < 400:
            level = logging.DEBUG
        elif status >= 500:
            level = logging.WARNING
        else:
            level = logging.INFO

        query = f"?{raw_query}" if raw_query and log.isEnabledFor(logging.DEBUG) else ""
        log.log(
            level,
            "%s %s%s -> %d in %dms",
            method,
            path,
            query,
            status,
            timer.ms,
            extra={
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": timer.ms,
                "client": scope["client"][0] if scope.get("client") else None,
            },
        )
