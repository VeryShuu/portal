from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr


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


class PatchRoleRequest(BaseModel):
    role: str
