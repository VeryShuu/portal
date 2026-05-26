"""Pydantic schemas for the extended KB API (permissions, files, diff, import).

Extracted from ``app.api.kb_extra`` so that handlers stay thin and schemas can
be reused without pulling in router dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PermissionEntry(BaseModel):
    id: uuid.UUID | None = None
    subject_type: str
    subject_id: str
    subject_name: str
    permission: str
    granted_by: uuid.UUID | None = None
    created_at: datetime | None = None
    email: str | None = None
    is_creator: bool = False

    model_config = {"from_attributes": True}


class PermissionList(BaseModel):
    items: list[PermissionEntry]


class SetPermissionRequest(BaseModel):
    subject_type: str = Field(..., pattern="^(user|group)$")
    subject_id: str = Field(min_length=1, max_length=255)
    subject_name: str = Field(min_length=1, max_length=255)
    permission: str = Field(..., pattern="^(viewer|editor|manager)$")


class InheritRequest(BaseModel):
    inherit_permissions: bool


class KbFilePublic(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    filename: str
    original_name: str
    size_bytes: int
    mime_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class KbFileList(BaseModel):
    items: list[KbFilePublic]


class MediaUploadResponse(BaseModel):
    url: str
    filename: str


class UserSearchResult(BaseModel):
    subject_type: str
    subject_id: str
    subject_name: str
    email: str | None = None


class DiffHunk(BaseModel):
    header: str
    lines: list[str]


class DiffResponse(BaseModel):
    hunks: list[DiffHunk]
    stats: dict[str, int]


class ImportReport(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
