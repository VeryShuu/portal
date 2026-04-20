from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NewsAuthor(BaseModel):
    id: uuid.UUID
    full_name: str
    department: str | None
    avatar_url: str | None

    model_config = {"from_attributes": True}


class NewsPublic(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    status: str
    is_pinned: bool
    category: str | None
    target_departments: list[str] | None
    target_roles: list[str] | None
    author_id: uuid.UUID | None
    publish_at: datetime | None
    archive_at: datetime | None
    published_at: datetime | None
    view_count: int
    current_version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NewsWithAuthor(NewsPublic):
    author: NewsAuthor | None


class NewsList(BaseModel):
    items: list[NewsPublic]
    total: int


class NewsVersionPublic(BaseModel):
    id: uuid.UUID
    news_id: uuid.UUID
    version: int
    title: str
    body: str
    editor_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateNewsRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="")
    status: str = Field(default="draft")
    is_pinned: bool = False
    category: str | None = Field(default=None, max_length=100)
    target_departments: list[str] | None = None
    target_roles: list[str] | None = None
    publish_at: datetime | None = None
    archive_at: datetime | None = None


class UpdateNewsRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    status: str | None = None
    is_pinned: bool | None = None
    category: str | None = None
    target_departments: list[str] | None = None
    target_roles: list[str] | None = None
    publish_at: datetime | None = None
    archive_at: datetime | None = None
