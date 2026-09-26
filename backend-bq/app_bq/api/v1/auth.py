"""Registration, login, refresh, logout, password reset: the BigQuery twin of app/api/v1/auth.py.

The cookie helpers are shared with the Postgres API, so both set exactly the same cookies.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from app.api.v1.auth import SAME_ANSWER, _clear_cookies, _client, _fail, _set_cookies
from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.schemas.auth import (
    ForgotPasswordIn,
    ForgotPasswordOut,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    UserOut,
)
from app_bq.api.deps import current_user
from app_bq.core.bq import BigQueryDB, Row, get_db
from app_bq.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("knowhub.auth")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterIn,
    request: Request,
    response: Response,
    db: BigQueryDB = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Row:
    """Create an account and sign in straight away."""
    try:
        user = await auth_service.register(db, data)
    except auth_service.AuthError as exc:
        raise _fail(exc) from exc
    batch = db.batch()
    user_agent, ip = _client(request)
    refresh_token = auth_service.issue_refresh_token(batch, settings, user, user_agent=user_agent, ip=ip)
    await batch.commit()
    _set_cookies(response, settings, create_access_token(settings, user.id, user.role), refresh_token)
    return user


@router.post("/login", response_model=UserOut)
async def login(
    data: LoginIn,
    request: Request,
    response: Response,
    db: BigQueryDB = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Row:
    batch = db.batch()
    try:
        user = await auth_service.authenticate(db, batch, data.email, data.password)
    except auth_service.AuthError as exc:
        await batch.commit()  # keep the failed-attempt counter
        raise _fail(exc) from exc
    user_agent, ip = _client(request)
    refresh_token = auth_service.issue_refresh_token(batch, settings, user, user_agent=user_agent, ip=ip)
    await batch.commit()
    _set_cookies(response, settings, create_access_token(settings, user.id, user.role), refresh_token)
    return user


@router.post("/refresh", response_model=UserOut)
async def refresh(
    request: Request,
    response: Response,
    db: BigQueryDB = Depends(get_db),
    settings: Settings = Depends(get_settings),
    knowhub_refresh: str | None = Cookie(default=None),
) -> Row:
    """Swap the refresh cookie for a new pair. The old token stops working."""
    if not knowhub_refresh:
        raise HTTPException(status_code=401, detail={"message": "Not signed in"})
    batch = db.batch()
    try:
        user_agent, ip = _client(request)
        user, new_refresh = await auth_service.rotate_refresh_token(
            db, batch, settings, knowhub_refresh, user_agent=user_agent, ip=ip
        )
    except auth_service.AuthError as exc:
        await batch.commit()
        _clear_cookies(response)
        raise _fail(exc) from exc
    await batch.commit()
    _set_cookies(response, settings, create_access_token(settings, user.id, user.role), new_refresh)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: BigQueryDB = Depends(get_db),
    knowhub_refresh: str | None = Cookie(default=None),
) -> None:
    """Sign out on this device. Always succeeds, so the browser can clean up."""
    if knowhub_refresh:
        batch = db.batch()
        auth_service.revoke_refresh_token(batch, knowhub_refresh)
        await batch.commit()
    _clear_cookies(response)


@router.post("/forgot-password", response_model=ForgotPasswordOut, status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    data: ForgotPasswordIn,
    request: Request,
    db: BigQueryDB = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ForgotPasswordOut:
    """Start a password reset. Same answer whether or not the address has an account;
    the link goes to the API log (and, locally, the response) until mail is wired up."""
    user_agent, ip = _client(request)
    batch = db.batch()
    result = await auth_service.start_password_reset(
        db, batch, settings, data.email, user_agent=user_agent, ip=ip
    )
    await batch.commit()

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
    db: BigQueryDB = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    """Set a new password from a reset link, and sign every device out."""
    batch = db.batch()
    try:
        await auth_service.complete_password_reset(db, batch, settings, data.token, data.password)
    except auth_service.AuthError as exc:
        raise _fail(exc) from exc
    await batch.commit()
    _clear_cookies(response)


@router.get("/me", response_model=UserOut)
async def me(user: Row = Depends(current_user)) -> Row:
    return user
