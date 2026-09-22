import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

HANDLE_PATTERN = r"^[a-z0-9][a-z0-9_.-]{2,29}$"


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=100)
    handle: str | None = Field(default=None, pattern=HANDLE_PATTERN)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.strip().lower()


class ForgotPasswordIn(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class ForgotPasswordOut(BaseModel):
    """The message is deliberately the same whether or not the email is registered."""

    message: str
    # only filled in locally, where there is no mail server to deliver the link
    reset_url: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    handle: str
    avatar_url: str | None
    bio: str | None
    role: str
    team_id: uuid.UUID | None = None
    created_at: datetime
