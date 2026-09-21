import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

VideoType = str
Category = str


class LinkIn(BaseModel):
    kind: str = "other"
    url: str = Field(min_length=4, max_length=2048)
    label: str | None = Field(default=None, max_length=200)

    @field_validator("url")
    @classmethod
    def must_be_http(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("Links must start with http:// or https://")
        return value


class SnippetIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    language: str = Field(default="text", pattern=r"^[a-z0-9+#.-]{1,20}$")
    code: str = Field(min_length=1, max_length=20000)


class LinkOut(LinkIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class SnippetOut(SnippetIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    title: str
    description: str | None
    category: str
    visibility: str
    status: str
    duration_sec: int | None
    size_bytes: int | None
    view_count: int
    like_count: int
    comment_count: int
    published_at: datetime | None
    created_at: datetime

    owner_id: uuid.UUID
    owner_display_name: str | None = None
    owner_handle: str | None = None
    topic_slug: str | None = None
    topic_name: str | None = None
    has_thumbnail: bool = False
    comments_enabled: bool = True
    links: list[LinkOut] = []
    snippets: list[SnippetOut] = []


class VideoPage(BaseModel):
    items: list[VideoOut]
    next_cursor: str | None = None


class VideoUpdate(BaseModel):
    """Everything the owner can change from their channel. Fields left out stay as
    they are; "" clears the description or the topic."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    category: str | None = None
    topic_slug: str | None = None
    visibility: str | None = None
    comments_enabled: bool | None = None
    # only meaningful with visibility="restricted"; replaces the whole list
    viewer_ids: list[uuid.UUID] | None = None
    links: list[LinkIn] | None = None
    snippets: list[SnippetIn] | None = None


class Person(BaseModel):
    id: uuid.UUID
    display_name: str
    handle: str


class ChannelVideo(VideoOut):
    """A video as its owner sees it in their channel, with the people it is shared with."""

    allowed_viewers: list[Person] = []


class Channel(BaseModel):
    id: uuid.UUID
    handle: str
    display_name: str
    bio: str | None
    avatar_url: str | None
    joined_at: datetime
    is_me: bool
    video_count: int
    total_views: int
    videos: list[ChannelVideo]
