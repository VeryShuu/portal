"""Pydantic-схемы для системы обратной связи."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedbackCategory(StrEnum):
    bug = "bug"
    suggestion = "suggestion"
    other = "other"


class FeedbackStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    closed = "closed"


def _validate_page_url(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    if len(s) > 2000:
        raise ValueError("Invalid page_url")
    if s.startswith("//"):
        raise ValueError("Invalid page_url")
    if s.startswith("/"):
        return s
    parsed = urlparse(s)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Invalid page_url")
    return s


class FeedbackIn(BaseModel):
    category: FeedbackCategory
    message: str = Field(default="", max_length=5000)
    page_url: str | None = Field(default=None, max_length=2000)

    @field_validator("message", mode="before")
    @classmethod
    def _strip_message(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("page_url", mode="before")
    @classmethod
    def _validate_page_url(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            return _validate_page_url(v)
        return v


class FeedbackReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)

    @field_validator("message", mode="before")
    @classmethod
    def _strip_message(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class FeedbackStatusIn(BaseModel):
    status: FeedbackStatus


class FeedbackAttachmentOut(BaseModel):
    id: uuid.UUID
    original_name: str
    size_bytes: int
    mime_type: str | None
    created_at: datetime
    download_url: str

    model_config = ConfigDict(from_attributes=True)


class FeedbackReplyOut(BaseModel):
    id: uuid.UUID
    admin_id: uuid.UUID | None
    admin_name: str | None
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackOut(BaseModel):
    id: uuid.UUID
    category: FeedbackCategory
    message: str
    page_url: str | None
    status: FeedbackStatus
    created_at: datetime
    updated_at: datetime
    replies: list[FeedbackReplyOut] = []
    attachments: list[FeedbackAttachmentOut] = []

    model_config = ConfigDict(from_attributes=True)


class FeedbackAdminOut(FeedbackOut):
    user_id: uuid.UUID | None
    author_name: str | None
    author_email: str | None


class FeedbackListOut(BaseModel):
    items: list[FeedbackOut]
    total: int


class FeedbackAdminListOut(BaseModel):
    items: list[FeedbackAdminOut]
    total: int
