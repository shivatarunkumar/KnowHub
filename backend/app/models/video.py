import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey

VIDEO_TYPES = ("video", "short")
CATEGORIES = (
    "bug_fix",
    "incident_resolution",
    "how_to",
    "knowledge_share",
    "demo",
    "reusable_component",
)
# internal = everyone signed in or not; unlisted = link only; restricted = the people
# listed in video_viewers; private = the owner alone.
VISIBILITIES = ("internal", "unlisted", "restricted", "private")


class Video(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "videos"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str]
    title: Mapped[str]
    description: Mapped[str | None]
    category: Mapped[str]
    primary_topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    visibility: Mapped[str] = mapped_column(default="internal")
    status: Mapped[str] = mapped_column(default="UPLOADING")
    environment: Mapped[str | None]
    severity: Mapped[str | None]
    original_filename: Mapped[str | None]
    mime_type: Mapped[str | None]
    raw_gcs_path: Mapped[str | None]
    hls_path: Mapped[str | None]
    thumbnail_path: Mapped[str | None]
    duration_sec: Mapped[int | None]
    width: Mapped[int | None]
    height: Mapped[int | None]
    size_bytes: Mapped[int | None]
    comments_enabled: Mapped[bool] = mapped_column(default=True)
    view_count: Mapped[int] = mapped_column(default=0)
    like_count: Mapped[int] = mapped_column(default=0)
    comment_count: Mapped[int] = mapped_column(default=0)
    processing_error: Mapped[str | None]
    published_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]
    current_edit_version: Mapped[int | None]


class UploadEvent(UUIDPrimaryKey, Base):
    __tablename__ = "upload_events"

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event: Mapped[str]
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime]


class VideoViewer(Base):
    """Who may watch a video whose visibility is 'restricted'."""

    __tablename__ = "video_viewers"

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]


LINK_KINDS = ("incident", "jira", "repo", "pr", "doc", "confluence", "other")


class VideoLink(UUIDPrimaryKey, Base):
    """A link shown under the video: runbook, ticket, repo, pull request, doc."""

    __tablename__ = "video_links"

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    kind: Mapped[str]
    url: Mapped[str]
    label: Mapped[str | None]
    created_at: Mapped[datetime]


class VideoSnippet(UUIDPrimaryKey, Base):
    """A block of code or config viewers can copy, instead of retyping it from the video."""

    __tablename__ = "video_snippets"

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    title: Mapped[str | None]
    language: Mapped[str] = mapped_column(default="text")
    code: Mapped[str]
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime]
