"""The signed-in user, from the access-token cookie: the BigQuery twin of app/api/deps.py.

Same cookies, same reasons logged for every 401. The difference is a short cache: a
BigQuery lookup costs a few hundred milliseconds, and the watch page alone makes a dozen
authenticated requests (the player's range requests, thumbnails, comments). A user is
kept for USER_CACHE_SECONDS, and dropped at once whenever this API changes their row.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import Cookie, Depends, HTTPException, status

from app.api.deps import ACCESS_COOKIE, REFRESH_COOKIE  # noqa: F401  (re-exported for the routers)
from app.core.config import Settings, get_settings
from app.core.logging import user_var
from app.core.security import decode_access_token
from app_bq.core.bq import BigQueryDB, Row, get_db

log = logging.getLogger("knowhub.auth")

USER_CACHE_SECONDS = 30
_users: dict[uuid.UUID, tuple[float, Row]] = {}


def forget_user(user_id: uuid.UUID) -> None:
    """Call after changing a user's row, so the next request reads it fresh."""
    _users.pop(user_id, None)


def remember_user(user: Row) -> None:
    _users[user.id] = (time.monotonic() + USER_CACHE_SECONDS, user)


async def load_user(db: BigQueryDB, user_id: uuid.UUID) -> Row | None:
    cached = _users.get(user_id)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    user = await db.row("SELECT * FROM {users} WHERE id = @id", id=user_id)
    if user is not None:
        remember_user(user)
    return user


async def current_user_optional(
    db: BigQueryDB = Depends(get_db),
    settings: Settings = Depends(get_settings),
    knowhub_access: str | None = Cookie(default=None),
) -> Row | None:
    """The signed-in user, or None. Anonymous is normal here, so reasons are DEBUG."""
    if not knowhub_access:
        log.debug("no %s cookie: treating as anonymous", ACCESS_COOKIE)
        return None

    claims = decode_access_token(settings, knowhub_access)
    if not claims:
        log.debug("access token rejected: expired, wrong signature, or not an access token")
        return None

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        log.warning("access token has no usable subject claim: %s", sorted(claims))
        return None

    user = await load_user(db, user_id)
    if user is None:
        log.warning("access token names user %s, who no longer exists", user_id)
        return None
    if not user.is_active or user.deleted_at is not None:
        log.info("user %s is deactivated; treating as signed out", user.handle)
        return None

    user_var.set(user.handle)
    log.debug("  signed in as %s (%s)", user.handle, user.role)
    return user


async def current_user(user: Row | None = Depends(current_user_optional)) -> Row:
    if user is None:
        log.info(
            "401: this endpoint needs an account and the request had no valid session "
            "(missing or expired %s cookie). The browser should refresh at "
            "POST /api/v1/auth/refresh, or the person signs in again",
            ACCESS_COOKIE,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def current_admin(user: Row = Depends(current_user)) -> Row:
    if user.role != "admin":
        log.info("403: %s is not an admin", user.handle)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user
