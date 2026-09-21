"""Shared FastAPI dependencies: the signed-in user, from the access-token cookie."""

from __future__ import annotations

import uuid

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import decode_access_token
from app.models.user import User

ACCESS_COOKIE = "knowhub_access"
REFRESH_COOKIE = "knowhub_refresh"


async def current_user_optional(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    knowhub_access: str | None = Cookie(default=None),
) -> User | None:
    """The signed-in user, or None. Used by public endpoints to personalise responses."""
    if not knowhub_access:
        return None
    claims = decode_access_token(settings, knowhub_access)
    if not claims:
        return None
    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        return None
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    return user


async def current_user(user: User | None = Depends(current_user_optional)) -> User:
    """The signed-in user, or 401. Used by everything that needs an account."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def current_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user
