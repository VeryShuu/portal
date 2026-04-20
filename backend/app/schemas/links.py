from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class ServiceLinkPublic(BaseModel):
    id: uuid.UUID
    title: str
    url: str
    icon_url: str | None
    description: str | None
    category: str | None
    sort_order: int
    supports_sso: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServiceLinkList(BaseModel):
    items: list[ServiceLinkPublic]
    total: int


class CreateLinkRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    icon_url: str | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    sort_order: int = Field(default=0, ge=0)
    supports_sso: bool = False
    is_active: bool = True


class UpdateLinkRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    icon_url: str | None = None
    description: str | None = None
    category: str | None = None
    sort_order: int | None = Field(default=None, ge=0)
    supports_sso: bool | None = None
    is_active: bool | None = None


class BookmarkPublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    url: str
    resource_type: str | None
    resource_id: str | None
    group_name: str | None
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BookmarkList(BaseModel):
    items: list[BookmarkPublic]
    total: int


class CreateBookmarkRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2048)
    resource_type: str | None = Field(default=None, max_length=50)
    resource_id: str | None = Field(default=None, max_length=100)
    group_name: str | None = Field(default=None, max_length=100)


class BookmarkReorderItem(BaseModel):
    id: uuid.UUID
    sort_order: int = Field(ge=0)


class ReorderBookmarksRequest(BaseModel):
    items: list[BookmarkReorderItem]
