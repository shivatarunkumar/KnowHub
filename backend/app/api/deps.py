"""Shared FastAPI dependencies: the signed-in user, from the access-token cookie.

A 401 from here is the most common "why doesn't this work?" in the app, so each way it can
happen is logged with its reason: no cookie at all, an expired or tampered token, or a user
who has since been deactivated.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.logging import user_var
from app.core.security import decode_access_token
from app.models.user import User

ACCESS_COOKIE = "knowhub_access"
REFRESH_COOKIE = "knowhub_refresh"

log = logging.getLogger("knowhub.auth")


async def current_user_optional(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    knowhub_access: str | None = Cookie(default=None),
) -> User | None:
    """The signed-in user, or None. Used by public endpoints to personalise responses.

    Anonymous is normal here, so the reasons are logged at DEBUG; current_user below
    repeats the reason at INFO when it turns one into a 401.
    """
    if not knowhub_access:
        log.debug("no %s cookie: treating as anonymous", ACCESS_COOKIE)
        return None

    claims = decode_access_token(settings, knowhub_access)
    if not claims:
        # expired is much the commoner case, but both look the same from here
        log.debug("access token rejected: expired, wrong signature, or not an access token")
        return None

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        log.warning("access token has no usable subject claim: %s", sorted(claims))
        return None

    user = await session.get(User, user_id)
    if user is None:
        log.warning("access token names user %s, who no longer exists", user_id)
        return None
    if not user.is_active or user.deleted_at is not None:
        log.info("user %s is deactivated; treating as signed out", user.handle)
        return None

    user_var.set(user.handle)  # every later log line in this request names them
    return user


async def current_user(user: User | None = Depends(current_user_optional)) -> User:
    """The signed-in user, or 401. Used by everything that needs an account."""
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


async def current_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        log.info("403: %s is not an admin", user.handle)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user
