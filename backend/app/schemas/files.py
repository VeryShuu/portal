"""Pydantic schemas for the file module (ADR-032)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── NC item (file or directory from WebDAV PROPFIND) ──────────────────────────

class NCItem(BaseModel):
    name: str
    nc_path: str
    is_dir: bool
    size_bytes: int = 0
    mime_type: str | None = None
    last_modified: datetime | None = None
    etag: str | None = None


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
    id: uuid.UUID
    folder_id: uuid.UUID
    subject_type: str
    subject_id: str
    subject_name: str
    permission: str
    granted_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PermissionList(BaseModel):
    items: list[PermissionPublic]


class GrantPermissionRequest(BaseModel):
    subject_type: str = Field(pattern="^(user|group)$")
    subject_id: str = Field(min_length=1, max_length=255)
    subject_name: str = Field(min_length=1, max_length=255)
    permission: str = Field(pattern="^(viewer|editor|manager)$")


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


# ── Folder detail (includes NC item list) ─────────────────────────────────────

class FolderDetailResponse(BaseModel):
    folder: FileFolderPublic
    items: list[NCItem]
    breadcrumbs: list[FileFolderPublic]
    nc_error: bool = False
