"""Registration, login, refresh, logout.

Tokens travel as httpOnly cookies, so JavaScript can't read them (an XSS bug can't
steal the session) and the browser sends them automatically. The web app and the API
are same-origin (Next.js proxies /api/* to FastAPI), so no CORS or CSRF token is
needed for this setup; cookies are SameSite=Lax, which blocks cross-site posts.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ACCESS_COOKIE, REFRESH_COOKIE, current_user
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordIn,
    ForgotPasswordOut,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    UserOut,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("knowhub.auth")

SAME_ANSWER = "If that email has an account, a reset link is on its way."


def _client(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), (request.client.host if request.client else None)


def _set_cookies(response: Response, settings: Settings, access_token: str, refresh_token: str) -> None:
    secure = not settings.is_local  # plain http on localhost, https everywhere else
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_ttl_min * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


def _fail(error: auth_service.AuthError) -> HTTPException:
    detail: dict = {"message": error.message}
    if error.field:
        detail["field"] = error.field
    return HTTPException(status_code=error.status_code, detail=detail)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Create an account and sign in straight away."""
    try:
        user = await auth_service.register(session, data)
        user_agent, ip = _client(request)
        refresh_token = await auth_service.issue_refresh_token(
            session, settings, user, user_agent=user_agent, ip=ip
        )
    except auth_service.AuthError as exc:
        raise _fail(exc) from exc
    await session.commit()
    _set_cookies(response, settings, create_access_token(settings, user.id, user.role), refresh_token)
    return user


@router.post("/login", response_model=UserOut)
async def login(
    data: LoginIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    try:
        user = await auth_service.authenticate(session, data.email, data.password)
        user_agent, ip = _client(request)
        refresh_token = await auth_service.issue_refresh_token(
            session, settings, user, user_agent=user_agent, ip=ip
        )
    except auth_service.AuthError as exc:
        await session.commit()  # keep the failed-attempt counter
        raise _fail(exc) from exc
    await session.commit()
    _set_cookies(response, settings, create_access_token(settings, user.id, user.role), refresh_token)
    return user


@router.post("/refresh", response_model=UserOut)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    knowhub_refresh: str | None = Cookie(default=None),
) -> User:
    """Swap the refresh cookie for a new pair. The old token stops working."""
    if not knowhub_refresh:
        raise HTTPException(status_code=401, detail={"message": "Not signed in"})
    try:
        user_agent, ip = _client(request)
        user, new_refresh = await auth_service.rotate_refresh_token(
            session, settings, knowhub_refresh, user_agent=user_agent, ip=ip
        )
    except auth_service.AuthError as exc:
        await session.commit()
        _clear_cookies(response)
        raise _fail(exc) from exc
    await session.commit()
    _set_cookies(response, settings, create_access_token(settings, user.id, user.role), new_refresh)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: AsyncSession = Depends(get_session),
    knowhub_refresh: str | None = Cookie(default=None),
) -> None:
    """Sign out on this device. Always succeeds, so the browser can clean up."""
    if knowhub_refresh:
        await auth_service.revoke_refresh_token(session, knowhub_refresh)
        await session.commit()
    _clear_cookies(response)


@router.post("/forgot-password", response_model=ForgotPasswordOut, status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    data: ForgotPasswordIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ForgotPasswordOut:
    """Start a password reset.

    The answer is identical whether or not the address has an account, so this cannot be
    used to find out who is registered.

    There is no mail server yet, so the link is written to the API log; running locally it
    also comes back in the response, which is the only way to use the flow on a laptop.
    Wiring a real provider means sending `reset_url` from here and nothing else changes.
    """
    user_agent, ip = _client(request)
    result = await auth_service.start_password_reset(
        session, settings, data.email, user_agent=user_agent, ip=ip
    )
    await session.commit()

    if result is None:
        log.info("password reset requested for an unknown address")
        return ForgotPasswordOut(message=SAME_ANSWER)

    user, token = result
    reset_url = f"{settings.web_base_url}/reset-password?token={token}"
    log.info(
        "password reset link for %s (valid %d minutes): %s",
        user.email,
        settings.password_reset_ttl_min,
        reset_url,
    )
    return ForgotPasswordOut(message=SAME_ANSWER, reset_url=reset_url if settings.is_local else None)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    data: ResetPasswordIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    """Set a new password from a reset link, and sign every device out."""
    try:
        await auth_service.complete_password_reset(session, settings, data.token, data.password)
    except auth_service.AuthError as exc:
        raise _fail(exc) from exc
    await session.commit()
    _clear_cookies(response)  # this browser included: sign in again with the new password


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user
