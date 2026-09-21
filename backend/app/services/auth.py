"""Registration, login and refresh-token rotation."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import Settings
from app.models.user import PasswordResetToken, RefreshToken, User
from app.schemas.auth import RegisterIn

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
HANDLE_RE = re.compile(r"[^a-z0-9_.-]+")


class AuthError(Exception):
    """Wrong credentials, duplicate email, locked account: reported to the user."""

    def __init__(self, message: str, *, status_code: int = 400, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.field = field


# ------------------------------------------------------------------ registration
def handle_from_email(email: str) -> str:
    """tarun.nagula@corp.com → tarun.nagula (a channel handle, written @tarun)."""
    base = HANDLE_RE.sub("", email.split("@", 1)[0].lower()).strip("._-")
    base = base or "user"
    if len(base) < 3:
        base = f"{base}user"
    return base[:30]


async def unique_handle(session: AsyncSession, wanted: str) -> str:
    """Append a number until the handle is free: tarun, tarun2, tarun3 …"""
    candidate, suffix = wanted, 1
    while await session.scalar(select(User.id).where(User.handle == candidate)):
        suffix += 1
        tail = str(suffix)
        candidate = f"{wanted[: 30 - len(tail)]}{tail}"
    return candidate


async def register(session: AsyncSession, data: RegisterIn) -> User:
    existing = await session.scalar(select(User.id).where(User.email == data.email))
    if existing:
        raise AuthError("An account with this email already exists", status_code=409, field="email")

    if data.handle:
        taken = await session.scalar(select(User.id).where(User.handle == data.handle))
        if taken:
            raise AuthError("That handle is taken", status_code=409, field="handle")
        handle = data.handle
    else:
        handle = await unique_handle(session, handle_from_email(data.email))

    user = User(
        email=data.email,
        password_hash=security.hash_password(data.password),
        password_changed_at=datetime.now(UTC),
        display_name=data.display_name,
        handle=handle,
        role="user",
        is_active=True,
        failed_login_count=0,
        subscriber_count=0,
    )
    session.add(user)
    await session.flush()
    return user


# ------------------------------------------------------------------ login
async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    now = datetime.now(UTC)

    # Same message whichever check fails, so the response can't be used to discover
    # which email addresses have accounts.
    invalid = AuthError("Incorrect email or password", status_code=401)

    if user is None:
        security.hash_password(password)  # keep the timing similar to a real check
        raise invalid
    if not user.is_active:
        raise AuthError("This account is disabled", status_code=403)
    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise AuthError(f"Too many failed attempts. Try again in {minutes} minute(s).", status_code=429)

    if not security.verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        raise invalid

    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    return user


# ------------------------------------------------------------------ refresh tokens
async def issue_refresh_token(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    token, token_hash = security.new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:500] or None,
            ip=ip,
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return token


async def rotate_refresh_token(
    session: AsyncSession,
    settings: Settings,
    token: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, str]:
    """Swap a refresh token for a new one. Reusing a revoked token logs the user out
    everywhere, because it means someone else has a copy."""
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_refresh_token(token))
    )
    if row is None:
        raise AuthError("Your session has expired. Please sign in again.", status_code=401)

    now = datetime.now(UTC)
    if row.revoked_at is not None:
        await revoke_all_for_user(session, row.user_id, reason="reuse_detected")
        raise AuthError("Your session was ended for security reasons. Please sign in again.", status_code=401)
    if row.expires_at <= now:
        raise AuthError("Your session has expired. Please sign in again.", status_code=401)

    user = await session.get(User, row.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthError("This account is no longer active", status_code=403)

    new_token, new_hash = security.new_refresh_token()
    replacement = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(user_agent or "")[:500] or None,
        ip=ip,
        created_at=now,
    )
    session.add(replacement)
    await session.flush()

    row.revoked_at = now
    row.revoked_reason = "rotated"
    row.replaced_by = replacement.id
    row.last_used_at = now
    return user, new_token


async def revoke_refresh_token(session: AsyncSession, token: str, reason: str = "logout") -> None:
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_refresh_token(token))
    )
    if row and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        row.revoked_reason = reason


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID, reason: str) -> None:
    rows = await session.scalars(
        select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    )
    for row in rows:
        row.revoked_at = func.now()
        row.revoked_reason = reason


# ------------------------------------------------------------------ password reset
async def start_password_reset(
    session: AsyncSession,
    settings: Settings,
    email: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, str] | None:
    """Create a reset token for this email, or return None if nobody owns it.

    The caller must answer the same way either way: telling an anonymous visitor whether
    an address has an account is an account-enumeration leak.
    """
    user = await session.scalar(
        select(User).where(User.email == email.strip().lower(), User.deleted_at.is_(None))
    )
    if user is None or not user.is_active:
        return None

    now = datetime.now(UTC)
    # any earlier link stops working the moment a new one is asked for
    outstanding = await session.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
        )
    )
    for row in outstanding:
        row.used_at = now

    token, token_hash = security.new_opaque_token()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=now + timedelta(minutes=settings.password_reset_ttl_min),
            requested_ip=ip,
            user_agent=user_agent,
            created_at=now,
        )
    )
    return user, token


async def complete_password_reset(
    session: AsyncSession, settings: Settings, token: str, password: str
) -> User:
    """Set the new password. The token works once, and only before it expires."""
    row = await session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == security.hash_token(token))
    )
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise AuthError(
            "That reset link is no longer valid. Please request a new one.", status_code=400, field="token"
        )

    user = await session.get(User, row.user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise AuthError("That reset link is no longer valid. Please request a new one.", status_code=400)

    user.password_hash = security.hash_password(password)
    user.password_changed_at = now
    # a reset is also how someone gets back in after locking themselves out
    user.failed_login_count = 0
    user.locked_until = None
    row.used_at = now

    # whoever else was signed in as this user is signed out: the password just changed
    await revoke_all_for_user(session, user.id, reason="password_reset")
    return user
