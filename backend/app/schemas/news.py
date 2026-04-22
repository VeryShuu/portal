from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


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
    cover_image: str | None = Field(default=None, exclude=True)
    cover_image_url: str | None = None
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

    @model_validator(mode="after")
    def build_cover_url(self) -> "NewsPublic":
        if self.cover_image:
            self.cover_image_url = f"/media/news/{self.cover_image}"
        return self


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


class GalleryImagePublic(BaseModel):
    id: uuid.UUID
    news_id: uuid.UUID
    filename: str = Field(exclude=True)
    url: str = ""
    original_name: str
    sort_order: int
    file_size: int | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def build_url(self) -> "GalleryImagePublic":
        self.url = f"/media/news/{self.news_id}/gallery/{self.filename}"
        return self


class AttachmentPublic(BaseModel):
    id: uuid.UUID
    news_id: uuid.UUID
    original_name: str
    mime_type: str | None
    file_size: int | None
    created_at: datetime
    download_url: str = ""

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def build_download_url(self) -> "AttachmentPublic":
        self.download_url = f"/api/v1/news/{self.news_id}/attachments/{self.id}/download"
        return self


class ReorderItem(BaseModel):
    id: uuid.UUID
    sort_order: int
