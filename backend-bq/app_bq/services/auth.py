"""Registration, login, refresh-token rotation and password reset, on BigQuery.

The rules, messages and log lines are the Postgres ones (app/services/auth.py); only the
data access differs. BigQuery has no unique indexes, so "one account per email" and
"one owner per handle" are enforced by a guarded INSERT ... WHERE NOT EXISTS.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.core import security
from app.core.config import Settings
from app.schemas.auth import RegisterIn
from app.services.auth import LOCKOUT_MINUTES, MAX_FAILED_LOGINS, AuthError, handle_from_email
from app_bq.api.deps import forget_user, remember_user
from app_bq.core.bq import NOW, Batch, BigQueryDB, Row, Typed

__all__ = ["AuthError"]

log = logging.getLogger("knowhub.auth")


# ------------------------------------------------------------------ registration
async def unique_handle(db: BigQueryDB, wanted: str) -> str:
    """tarun, tarun2, tarun3 … in one query rather than one per guess."""
    taken = {
        row.handle
        for row in await db.rows(
            "SELECT handle FROM {users} WHERE STARTS_WITH(handle, @prefix)", prefix=wanted[:27]
        )
    }
    candidate, suffix = wanted, 1
    while candidate in taken:
        suffix += 1
        tail = str(suffix)
        candidate = f"{wanted[: 30 - len(tail)]}{tail}"
    return candidate


INSERT_USER = """
INSERT INTO {users} (id, email, password_hash, password_changed_at, display_name, handle, role,
                     is_active, failed_login_count, created_at, updated_at)
SELECT @id, @email, @password_hash, @now, @display_name, @handle, 'user', TRUE, 0, @now, @now
FROM UNNEST([1])
WHERE NOT EXISTS (SELECT 1 FROM {users} WHERE email = @email OR handle = @handle)
"""


async def register(db: BigQueryDB, data: RegisterIn) -> Row:
    handle = data.handle or await unique_handle(db, handle_from_email(data.email))
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    inserted = await db.execute(
        INSERT_USER,
        id=user_id,
        email=data.email,
        password_hash=security.hash_password(data.password),
        now=now,
        display_name=data.display_name,
        handle=handle,
    )
    if not inserted:
        clash = await db.row(
            "SELECT email = @email AS same_email FROM {users} "
            "WHERE email = @email OR handle = @handle LIMIT 1",
            email=data.email,
            handle=handle,
        )
        if clash is None or clash.same_email:
            raise AuthError("An account with this email already exists", status_code=409, field="email")
        raise AuthError("That handle is taken", status_code=409, field="handle")

    return Row(
        id=user_id,
        email=data.email,
        display_name=data.display_name,
        handle=handle,
        avatar_url=None,
        bio=None,
        role="user",
        team_id=None,
        is_active=True,
        deleted_at=None,
        created_at=now,
    )


# ------------------------------------------------------------------ login
async def authenticate(db: BigQueryDB, batch: Batch, email: str, password: str) -> Row:
    """Check the password. The caller commits `batch`, which holds the counter updates
    (a failed attempt is recorded even though this raises)."""
    user = await db.row(
        "SELECT * FROM {users} WHERE email = @email AND deleted_at IS NULL ORDER BY created_at LIMIT 1",
        email=email,
    )
    now = datetime.now(UTC)
    invalid = AuthError("Incorrect email or password", status_code=401)

    if user is None:
        security.hash_password(password)  # keep the timing similar to a real check
        log.info("login failed: no account for that email (the reply does not say so)")
        raise invalid
    if not user.is_active:
        log.info("login refused: %s is deactivated", user.handle)
        raise AuthError("This account is disabled", status_code=403)
    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        log.info("login refused: %s is locked for another %d minute(s)", user.handle, minutes)
        raise AuthError(f"Too many failed attempts. Try again in {minutes} minute(s).", status_code=429)

    forget_user(user.id)
    if not security.verify_password(password, user.password_hash):
        failures = user.failed_login_count + 1
        if failures >= MAX_FAILED_LOGINS:
            batch.update(
                "users",
                {"id": user.id},
                {"failed_login_count": 0, "locked_until": now + timedelta(minutes=LOCKOUT_MINUTES)},
            )
            log.warning(
                "%s locked for %d minutes after %d failed attempts",
                user.handle,
                LOCKOUT_MINUTES,
                MAX_FAILED_LOGINS,
            )
        else:
            batch.update("users", {"id": user.id}, {"failed_login_count": failures})
            log.info(
                "login failed: wrong password for %s (attempt %d of %d)",
                user.handle,
                failures,
                MAX_FAILED_LOGINS,
            )
        raise invalid

    changes: dict = {"failed_login_count": 0, "locked_until": None, "last_login_at": now}
    if security.needs_rehash(user.password_hash):
        changes["password_hash"] = security.hash_password(password)
    batch.update("users", {"id": user.id}, changes)
    user.update(changes)
    log.info("signed in: %s", user.handle)
    return user


# ------------------------------------------------------------------ refresh tokens
def issue_refresh_token(
    batch: Batch,
    settings: Settings,
    user: Row,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    token, token_hash = security.new_refresh_token()
    now = datetime.now(UTC)
    batch.insert(
        "refresh_tokens",
        {
            "id": uuid.uuid4(),
            "user_id": user.id,
            "token_hash": token_hash,
            "expires_at": now + timedelta(days=settings.refresh_token_ttl_days),
            "user_agent": (user_agent or "")[:500] or None,
            "ip": ip,
            "created_at": now,
        },
    )
    return token


TOKEN_AND_USER = """
SELECT u.*, t.id AS token_id, t.user_id AS token_user_id,
       t.revoked_at AS token_revoked_at, t.expires_at AS token_expires_at
FROM {refresh_tokens} AS t
LEFT JOIN {users} AS u ON u.id = t.user_id
WHERE t.token_hash = @token_hash
LIMIT 1
"""

# Rotation in one statement: the old token (matched) is revoked and pointed at its
# successor, the new one (not matched) is inserted. Two statements on the same table
# would have to run one after the other, at ~2s each.
ROTATE = """
MERGE {refresh_tokens} AS t
USING (
  SELECT @old_id AS id, @user_id AS user_id, CAST(NULL AS STRING) AS token_hash,
         CAST(NULL AS TIMESTAMP) AS expires_at, CAST(NULL AS STRING) AS user_agent, CAST(NULL AS STRING) AS ip
  UNION ALL
  SELECT @new_id, @user_id, @new_hash, @expires_at, @user_agent, @ip
) AS s
ON t.id = s.id
WHEN MATCHED AND t.revoked_at IS NULL THEN
  UPDATE SET revoked_at = @now, revoked_reason = 'rotated', replaced_by = @new_id, last_used_at = @now
WHEN NOT MATCHED THEN
  INSERT (id, user_id, token_hash, expires_at, user_agent, ip, created_at)
  VALUES (s.id, s.user_id, s.token_hash, s.expires_at, s.user_agent, s.ip, @now)
"""


async def rotate_refresh_token(
    db: BigQueryDB,
    batch: Batch,
    settings: Settings,
    token: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[Row, str]:
    """Swap a refresh token for a new one. Reusing a revoked token logs the user out
    everywhere, because it means someone else has a copy."""
    row = await db.row(TOKEN_AND_USER, token_hash=security.hash_refresh_token(token))
    if row is None:
        raise AuthError("Your session has expired. Please sign in again.", status_code=401)

    now = datetime.now(UTC)
    if row.token_revoked_at is not None:
        log.warning(
            "refresh token reuse detected for user %s: revoking every session they have",
            row.token_user_id,
        )
        revoke_all_for_user(batch, row.token_user_id, reason="reuse_detected")
        raise AuthError("Your session was ended for security reasons. Please sign in again.", status_code=401)
    if row.token_expires_at <= now:
        raise AuthError("Your session has expired. Please sign in again.", status_code=401)
    if row.id is None or not row.is_active or row.deleted_at is not None:
        raise AuthError("This account is no longer active", status_code=403)

    new_token, new_hash = security.new_refresh_token()
    await db.execute(
        ROTATE,
        old_id=row.token_id,
        new_id=uuid.uuid4(),
        user_id=row.id,
        new_hash=new_hash,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=Typed((user_agent or "")[:500] or None, "STRING"),
        ip=Typed(ip, "STRING"),
        now=now,
    )
    user = Row({k: v for k, v in row.items() if not k.startswith("token_")})
    remember_user(user)
    return user, new_token


def revoke_refresh_token(batch: Batch, token: str, reason: str = "logout") -> None:
    batch.execute(
        "UPDATE {refresh_tokens} SET revoked_at = CURRENT_TIMESTAMP(), revoked_reason = @reason "
        "WHERE token_hash = @token_hash AND revoked_at IS NULL",
        reason=reason,
        token_hash=security.hash_refresh_token(token),
    )


def revoke_all_for_user(batch: Batch, user_id: uuid.UUID, reason: str) -> None:
    batch.update(
        "refresh_tokens",
        {"user_id": user_id, "revoked_at": None},
        {"revoked_at": NOW, "revoked_reason": reason},
    )


# ------------------------------------------------------------------ password reset
async def start_password_reset(
    db: BigQueryDB,
    batch: Batch,
    settings: Settings,
    email: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[Row, str] | None:
    """Create a reset token for this email, or return None if nobody owns it. The caller
    answers the same way either way (no account enumeration)."""
    user = await db.row(
        "SELECT * FROM {users} WHERE email = @email AND deleted_at IS NULL LIMIT 1",
        email=email.strip().lower(),
    )
    if user is None or not user.is_active:
        return None

    now = datetime.now(UTC)
    # any earlier link stops working the moment a new one is asked for
    batch.update("password_reset_tokens", {"user_id": user.id, "used_at": None}, {"used_at": now})
    token, token_hash = security.new_opaque_token()
    batch.insert(
        "password_reset_tokens",
        {
            "id": uuid.uuid4(),
            "user_id": user.id,
            "token_hash": token_hash,
            "expires_at": now + timedelta(minutes=settings.password_reset_ttl_min),
            "requested_ip": ip,
            "user_agent": user_agent,
            "created_at": now,
        },
    )
    return user, token


async def complete_password_reset(
    db: BigQueryDB, batch: Batch, settings: Settings, token: str, password: str
) -> Row:
    """Set the new password. The token works once, and only before it expires."""
    row = await db.row(
        """
        SELECT t.id, t.used_at, t.expires_at, u.id AS user_id,
               u.is_active AND u.deleted_at IS NULL AS user_ok
        FROM {password_reset_tokens} AS t LEFT JOIN {users} AS u ON u.id = t.user_id
        WHERE t.token_hash = @token_hash LIMIT 1
        """,
        token_hash=security.hash_token(token),
    )
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise AuthError(
            "That reset link is no longer valid. Please request a new one.", status_code=400, field="token"
        )
    if row.user_id is None or not row.user_ok:
        raise AuthError("That reset link is no longer valid. Please request a new one.", status_code=400)

    batch.update(
        "users",
        {"id": row.user_id},
        {
            "password_hash": security.hash_password(password),
            "password_changed_at": now,
            # a reset is also how someone gets back in after locking themselves out
            "failed_login_count": 0,
            "locked_until": None,
        },
    )
    batch.update("password_reset_tokens", {"id": row.id, "used_at": None}, {"used_at": now})
    revoke_all_for_user(batch, row.user_id, reason="password_reset")
    forget_user(row.user_id)
    return Row(id=row.user_id)
