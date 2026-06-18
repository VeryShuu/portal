from __future__ import annotations

import contextlib
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


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
    categories: list[str]
    cover_image: str | None = Field(default=None, exclude=True)
    cover_image_url: str | None = None
    cover_focal_x: int | None = None
    cover_focal_y: int | None = None
    cover_dominant_color: str | None = None
    cover_variants: list[int] | None = Field(default=None, exclude=True)
    cover_webp_srcset: str | None = None
    cover_avif_srcset: str | None = None
    target_departments: list[str] | None
    target_roles: list[str] | None
    author_id: uuid.UUID | None
    publish_at: datetime | None
    archive_at: datetime | None
    published_at: datetime | None
    deleted_at: datetime | None = None
    view_count: int
    like_count: int = 0
    liked_by_me: bool = False
    comment_count: int = 0
    current_version: int
    created_at: datetime
    updated_at: datetime
    has_poll: bool = False

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def check_poll(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            with contextlib.suppress(Exception):
                data.has_poll = getattr(data, "poll", None) is not None
        elif "poll" in data:
            data["has_poll"] = data["poll"] is not None
        return data

    @model_validator(mode="after")
    def build_cover_url(self) -> NewsPublic:
        if self.cover_image:
            v = int(self.updated_at.timestamp()) if self.updated_at else 0
            self.cover_image_url = f"/media/news/{self.cover_image}?v={v}"
            if self.cover_variants:
                base = f"/media/news/{self.id}/cover"
                webp_parts = [f"{base}-{w}.webp?v={v} {w}w" for w in self.cover_variants]
                avif_parts = [f"{base}-{w}.avif?v={v} {w}w" for w in self.cover_variants]
                self.cover_webp_srcset = ", ".join(webp_parts)
                self.cover_avif_srcset = ", ".join(avif_parts)
        return self


class NewsWithAuthor(NewsPublic):
    author: NewsAuthor | None
    previous_status: str | None = None


class NewsList(BaseModel):
    items: list[NewsPublic]
    total: int


class NewsLikeState(BaseModel):
    like_count: int
    liked_by_me: bool


class NewsCommentPublic(BaseModel):
    id: uuid.UUID
    news_id: uuid.UUID
    body: str | None
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime
    author: NewsAuthor | None = None


class NewsCommentList(BaseModel):
    items: list[NewsCommentPublic]
    total: int


class CreateNewsCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class UpdateNewsCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class TrashNewsList(BaseModel):
    items: list[NewsWithAuthor]
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


def _check_focal_coord(value: int | None, field: str) -> None:
    if value is not None and not (0 <= value <= 100):
        raise ValueError(f"{field} must be between 0 and 100")


def _normalize_str_list(v: object) -> object:
    """Coerce empty string or empty list to None; strip whitespace from items."""
    if v is None or v == "" or v == []:
        return None
    if isinstance(v, list):
        filtered = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        return filtered or None
    return v


class CreateNewsRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="")
    status: str = Field(default="draft")
    is_pinned: bool = False
    categories: list[str] = Field(default_factory=list)
    target_departments: list[str] | None = None
    target_roles: list[str] | None = None
    publish_at: datetime | None = None
    archive_at: datetime | None = None
    cover_focal_x: int | None = None
    cover_focal_y: int | None = None

    @field_validator("target_departments", "target_roles", mode="before")
    @classmethod
    def _normalize_deps(cls, v: object) -> object:
        return _normalize_str_list(v)

    @model_validator(mode="after")
    def _check_focal_point(self) -> CreateNewsRequest:
        _check_focal_coord(self.cover_focal_x, "cover_focal_x")
        _check_focal_coord(self.cover_focal_y, "cover_focal_y")
        return self


class UpdateNewsRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    status: str | None = None
    is_pinned: bool | None = None
    categories: list[str] | None = None
    target_departments: list[str] | None = None
    target_roles: list[str] | None = None
    publish_at: datetime | None = None
    archive_at: datetime | None = None
    published_at: datetime | None = None
    cover_focal_x: int | None = None
    cover_focal_y: int | None = None

    @field_validator("target_departments", "target_roles", mode="before")
    @classmethod
    def _normalize_deps(cls, v: object) -> object:
        return _normalize_str_list(v)

    @model_validator(mode="after")
    def _check_focal_point(self) -> UpdateNewsRequest:
        _check_focal_coord(self.cover_focal_x, "cover_focal_x")
        _check_focal_coord(self.cover_focal_y, "cover_focal_y")
        return self


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
    def build_url(self) -> GalleryImagePublic:
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
    def build_download_url(self) -> AttachmentPublic:
        self.download_url = f"/api/v1/news/{self.news_id}/attachments/{self.id}/download"
        return self


class ReorderItem(BaseModel):
    id: uuid.UUID
    sort_order: int


class NewsUploadLimits(BaseModel):
    news_attachment_max_size_mb: int


class NewsShareEmailRequest(BaseModel):
    recipient_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    message: str | None = Field(default=None, max_length=2000)


class NewsShareEmailResponse(BaseModel):
    enqueued: int
