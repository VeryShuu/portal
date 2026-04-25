"""Pydantic-схемы для модуля фотогалереи."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FolderRef(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class FolderPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    name: str
    slug: str
    path: str
    description: str | None = None
    cover_photo_id: uuid.UUID | None = None
    photos_count: int = 0
    children_count: int = 0
    permission: str | None = None  # вычисляемое поле для текущего пользователя
    created_at: datetime
    updated_at: datetime


class FolderTreeNode(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    name: str
    slug: str
    path: str
    cover_photo_id: uuid.UUID | None = None
    permission: str | None = None
    children: list["FolderTreeNode"] = Field(default_factory=list)


class FolderTree(BaseModel):
    items: list[FolderTreeNode]


class CreateFolderRequest(BaseModel):
    parent_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class UpdateFolderRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    cover_photo_id: uuid.UUID | None = None
    # None = сделать корневой; если поле отсутствует в model_fields_set — не менять
    parent_id: uuid.UUID | None = None


class PhotoPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    folder_id: uuid.UUID
    folder_path: str | None = None
    filename: str
    original_name: str
    size_bytes: int
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    taken_at: datetime | None = None
    description: str | None = None
    processed: bool
    uploaded_by: uuid.UUID | None = None
    created_at: datetime


class PhotoList(BaseModel):
    items: list[PhotoPublic]
    total: int
    page: int
    per_page: int


class UpdatePhotoRequest(BaseModel):
    description: str | None = None
    folder_id: uuid.UUID | None = None


class PermissionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    folder_id: uuid.UUID
    subject_type: str
    subject_id: str
    subject_name: str
    permission: str
    granted_by: uuid.UUID | None = None
    created_at: datetime


class PermissionList(BaseModel):
    items: list[PermissionPublic]


class GrantPermissionRequest(BaseModel):
    subject_type: str = Field(pattern=r"^(user|group)$")
    subject_id: str = Field(min_length=1, max_length=255)
    subject_name: str = Field(min_length=1, max_length=255)
    permission: str = Field(pattern=r"^(viewer|uploader|manager)$")


class UploadResultItem(BaseModel):
    photo_id: uuid.UUID | None = None
    original_name: str
    ok: bool
    error: str | None = None


class UploadResult(BaseModel):
    items: list[UploadResultItem]


class ShareLinkRequest(BaseModel):
    expires_in_days: int | None = Field(default=7, ge=1, le=365)


class ShareLinkPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    photo_id: uuid.UUID
    token: str
    url: str
    created_at: datetime
    expires_at: datetime | None = None


class ZipJobPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    folder_id: uuid.UUID
    status: str
    created_at: datetime
    expires_at: datetime | None = None
    download_url: str | None = None


class BulkActionRequest(BaseModel):
    action: str = Field(pattern=r"^(move|delete)$")
    photo_ids: list[uuid.UUID] = Field(min_length=1)
    target_folder_id: uuid.UUID | None = None


class BulkActionResponse(BaseModel):
    processed: int
    errors: list[str]
