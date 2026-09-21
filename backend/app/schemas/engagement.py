import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReactionIn(BaseModel):
    value: int = Field(ge=-1, le=1, description="1 like, -1 dislike, 0 removes the reaction")


class ReactionOut(BaseModel):
    like_count: int
    dislike_count: int
    my_reaction: int


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    parent_id: uuid.UUID | None = None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    video_id: uuid.UUID
    parent_id: uuid.UUID | None
    body: str
    like_count: int
    is_pinned: bool
    created_at: datetime
    edited_at: datetime | None
    author_id: uuid.UUID
    author_name: str
    author_handle: str
    liked_by_me: bool = False
    is_mine: bool = False
    is_uploader: bool = False
    editable_until: datetime | None = None
    replies: list["CommentOut"] = []


class ShareIn(BaseModel):
    to_user_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    message: str | None = Field(default=None, max_length=1000)
    at_seconds: int | None = Field(default=None, ge=0)


class UserSuggestion(BaseModel):
    id: uuid.UUID
    display_name: str
    handle: str


class SharedVideo(BaseModel):
    video_id: uuid.UUID
    title: str
    from_name: str
    from_handle: str
    message: str | None
    at_seconds: int | None
    created_at: datetime
