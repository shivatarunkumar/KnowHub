import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str]
    email_verified_at: Mapped[datetime | None]
    password_hash: Mapped[str]
    password_changed_at: Mapped[datetime]
    display_name: Mapped[str]
    handle: Mapped[str]
    avatar_url: Mapped[str | None]
    banner_url: Mapped[str | None]
    bio: Mapped[str | None]
    role: Mapped[str] = mapped_column(default="user")
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None]
    failed_login_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]
    subscriber_count: Mapped[int] = mapped_column(default=0)
    # the team this person works in; the upload form defaults to it
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))


class RefreshToken(UUIDPrimaryKey, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str]
    expires_at: Mapped[datetime]
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    revoked_reason: Mapped[str | None]
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("refresh_tokens.id"))
    user_agent: Mapped[str | None]
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime]


class PasswordResetToken(UUIDPrimaryKey, Base):
    """A single-use token proving someone can read the account's mailbox."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str]
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    requested_ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None]
    created_at: Mapped[datetime]
