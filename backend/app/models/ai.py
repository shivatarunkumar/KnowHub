import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKey


class AIRequest(UUIDPrimaryKey, Base):
    """One "Improve with AI" call: what was asked, how long it took, and whether the
    author kept the suggestion."""

    __tablename__ = "ai_requests"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    video_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"))
    field: Mapped[str]
    provider: Mapped[str]
    model: Mapped[str]
    input_chars: Mapped[int] = mapped_column(default=0)
    output_chars: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[int | None]
    accepted: Mapped[bool | None]
    error: Mapped[str | None]
    created_at: Mapped[datetime]
