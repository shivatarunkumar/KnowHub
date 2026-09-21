"""Registration, login, refresh, logout.

Tokens travel as httpOnly cookies, so JavaScript can't read them (an XSS bug can't
steal the session) and the browser sends them automatically. The web app and the API
are same-origin (Next.js proxies /api/* to FastAPI), so no CORS or CSRF token is
needed for this setup; cookies are SameSite=Lax, which blocks cross-site posts.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ACCESS_COOKIE, REFRESH_COOKIE, current_user
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import LoginIn, RegisterIn, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user
