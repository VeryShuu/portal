"""Pydantic schemas for the file module (ADR-032)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import MAX_BULK_FILES

# ── NC item (file or directory from WebDAV PROPFIND) ──────────────────────────


class UploadedByPublic(BaseModel):
    id: uuid.UUID
    full_name: str
    avatar_url: str | None = None


class NCItem(BaseModel):
    name: str
    nc_path: str
    is_dir: bool
    size_bytes: int = 0
    mime_type: str | None = None
    last_modified: datetime | None = None
    etag: str | None = None
    uploaded_at: datetime | None = None
    uploaded_by: UploadedByPublic | None = None


class NCItemList(BaseModel):
    items: list[NCItem]
    folder_nc_path: str


# ── Folder schemas ─────────────────────────────────────────────────────────────


class FileFolderPublic(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    nc_path: str
    description: str | None
    permission: str | None
    inherit_permissions: bool = True
    children_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FileFolderTreeNode(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    nc_path: str
    permission: str | None
    inherit_permissions: bool = True
    children: list[FileFolderTreeNode] = Field(default_factory=list)

    model_config = {"from_attributes": True}


FileFolderTreeNode.model_rebuild()


class FileFolderTree(BaseModel):
    items: list[FileFolderTreeNode]


class CreateFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    description: str | None = None


class UpdateFolderRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


# ── Permission schemas ─────────────────────────────────────────────────────────


class PermissionPublic(BaseModel):
    id: uuid.UUID | None = None
    folder_id: uuid.UUID
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
    items: list[PermissionPublic]


class GrantPermissionRequest(BaseModel):
    subject_type: str = Field(pattern="^(user|group)$")
    subject_id: str = Field(min_length=1, max_length=255)
    subject_name: str = Field(min_length=1, max_length=255)
    permission: str = Field(pattern="^(viewer|editor|manager)$")


# ── Per-file share schemas (sharing.md) ────────────────────────────────────────


class CreateFileShareRequest(BaseModel):
    subject_type: str = Field(pattern="^(user|group)$")
    subject_id: str = Field(min_length=1, max_length=255)
    subject_name: str = Field(min_length=1, max_length=255)
    permission: str = Field(pattern="^(viewer|editor)$")
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class FileSharePublic(BaseModel):
    id: uuid.UUID
    folder_id: uuid.UUID
    filename: str
    nc_path: str
    subject_type: str
    subject_id: str
    subject_name: str
    permission: str
    shared_by: uuid.UUID | None
    created_at: datetime
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class FileShareList(BaseModel):
    items: list[FileSharePublic]


class MyFileShare(BaseModel):
    id: uuid.UUID
    folder_id: uuid.UUID
    filename: str
    nc_path: str
    folder_name: str
    subject_type: str
    subject_id: str
    subject_name: str
    permission: str
    created_at: datetime
    expires_at: datetime | None


class MyFileShareList(BaseModel):
    items: list[MyFileShare]


class SharedFile(BaseModel):
    id: uuid.UUID
    folder_id: uuid.UUID
    filename: str
    nc_path: str
    folder_name: str
    permission: str
    shared_by_name: str | None = None
    created_at: datetime
    expires_at: datetime | None


class SharedFileList(BaseModel):
    items: list[SharedFile]


class AdminFileShare(BaseModel):
    id: uuid.UUID
    folder_id: uuid.UUID
    filename: str
    nc_path: str
    folder_name: str | None = None
    subject_type: str
    subject_id: str
    subject_name: str
    permission: str
    shared_by: uuid.UUID | None
    shared_by_name: str | None = None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class AdminFileShareList(BaseModel):
    items: list[AdminFileShare]
    total: int
    limit: int
    offset: int


# ── Upload / open schemas ──────────────────────────────────────────────────────


class UploadResultItem(BaseModel):
    name: str
    nc_path: str
    size_bytes: int
    success: bool
    error: str | None = None


class UploadResult(BaseModel):
    uploaded: list[UploadResultItem]
    failed: list[UploadResultItem]


class FileOpenResponse(BaseModel):
    type: str
    url: str
    display_name: str | None = None
    can_write: bool = True


# ── Folder detail (includes NC item list) ─────────────────────────────────────


class FolderDetailResponse(BaseModel):
    folder: FileFolderPublic
    items: list[NCItem]
    breadcrumbs: list[FileFolderPublic]
    nc_error: bool = False


# ── Bulk operations ────────────────────────────────────────────────────────────


class BulkDeleteRequest(BaseModel):
    filenames: list[str] = Field(min_length=1, max_length=MAX_BULK_FILES)


class BulkDeleteResultItem(BaseModel):
    name: str
    success: bool
    error: str | None = None


class BulkDeleteResult(BaseModel):
    deleted: list[BulkDeleteResultItem]
    failed: list[BulkDeleteResultItem]


class BulkMoveRequest(BaseModel):
    filenames: list[str] = Field(min_length=1, max_length=MAX_BULK_FILES)
    target_folder_id: uuid.UUID


class BulkMoveResultItem(BaseModel):
    name: str
    new_name: str | None = None
    success: bool
    error: str | None = None


class BulkMoveResult(BaseModel):
    moved: list[BulkMoveResultItem]
    failed: list[BulkMoveResultItem]
