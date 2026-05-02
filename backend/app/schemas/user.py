from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,63}$")


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    department: str | None
    position: str | None
    phone: str | None
    role: str
    avatar_url: str | None
    presence_status: str
    lang: str
    created_at: datetime
    auth_source: str
    attributes: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class UserMe(UserPublic):
    notify_email: bool
    notify_inapp: bool
    preferences: dict[str, Any]
    last_login_at: datetime | None


class UserList(BaseModel):
    items: list[UserPublic]
    total: int


class PatchProfileRequest(BaseModel):
    presence_status: str | None = None
    lang: str | None = None
    notify_email: bool | None = None
    notify_inapp: bool | None = None


class PatchPreferencesRequest(BaseModel):
    hidden_link_ids: list[str] | None = None
    onboarding_completed: bool | None = None


class PatchRoleRequest(BaseModel):
    role: str


class LocalLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v.lower()


class LocalUserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="reader")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v.lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("reader", "editor", "admin"):
            raise ValueError("role must be reader, editor or admin")
        return v


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminPatchProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = None
    position: str | None = None
    phone: str | None = None
