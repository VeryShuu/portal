"""Pydantic schemas for the object directories feature (docs/wip/directories.md).

Covers directory *types* (with their ``field_schema`` / ``channels``),
*entries* (objects) and their *contacts*. The field/channel definitions live as
JSONB on the type, validated here at the Pydantic layer (Literal for ``type``)
so adding a field never requires a migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

FieldType = Literal["text", "number", "email", "url", "multiline"]

_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"
_SLUG_PATTERN = r"^[a-z][a-z0-9_-]*$"
_ALLOWED_URL_SCHEMES = {"http", "https"}


def _validate_http_https_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError("Invalid URL") from exc
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        raise ValueError("URL must use http or https scheme")
    if not parsed.netloc:
        raise ValueError("URL must have a valid host")
    return url


def _ensure_unique_keys(items: list, what: str) -> None:
    keys = [item.key for item in items]
    if len(keys) != len(set(keys)):
        raise ValueError(f"Duplicate {what} keys are not allowed")


# ── Field schema / channels ───────────────────────────────────────────────────


class DirectoryField(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=_KEY_PATTERN)
    label_ru: str = Field(min_length=1, max_length=100)
    label_en: str | None = Field(default=None, max_length=100)
    type: FieldType = "text"
    required: bool = False
    sort_order: int = Field(default=0, ge=0)


class DirectoryChannel(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=_KEY_PATTERN)
    label_ru: str = Field(min_length=1, max_length=100)
    label_en: str | None = Field(default=None, max_length=100)
    sort_order: int = Field(default=0, ge=0)


# ── Directory (type) ───────────────────────────────────────────────────────────


class DirectoryPublic(BaseModel):
    id: uuid.UUID
    slug: str
    label_ru: str
    label_en: str | None
    icon: str | None
    description: str | None
    field_schema: list[DirectoryField]
    channels: list[DirectoryChannel]
    enabled: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DirectoryList(BaseModel):
    items: list[DirectoryPublic]
    total: int


class CreateDirectoryRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=50, pattern=_SLUG_PATTERN)
    label_ru: str = Field(min_length=1, max_length=100)
    label_en: str | None = Field(default=None, max_length=100)
    icon: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    field_schema: list[DirectoryField] = Field(default_factory=list)
    channels: list[DirectoryChannel] = Field(default_factory=list)
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_unique_keys(self) -> CreateDirectoryRequest:
        _ensure_unique_keys(self.field_schema, "field")
        _ensure_unique_keys(self.channels, "channel")
        return self


class UpdateDirectoryRequest(BaseModel):
    label_ru: str | None = Field(default=None, min_length=1, max_length=100)
    label_en: str | None = Field(default=None, max_length=100)
    icon: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    field_schema: list[DirectoryField] | None = None
    channels: list[DirectoryChannel] | None = None
    enabled: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_unique_keys(self) -> UpdateDirectoryRequest:
        if self.field_schema is not None:
            _ensure_unique_keys(self.field_schema, "field")
        if self.channels is not None:
            _ensure_unique_keys(self.channels, "channel")
        return self


# ── Contacts ────────────────────────────────────────────────────────────────────


class ContactPublic(BaseModel):
    id: uuid.UUID
    role: str | None
    channel: str
    label: str | None
    value: str
    sort_order: int

    model_config = {"from_attributes": True}


class ContactInput(BaseModel):
    role: str | None = Field(default=None, max_length=100)
    channel: str = Field(min_length=1, max_length=50)
    label: str | None = Field(default=None, max_length=200)
    value: str = Field(min_length=1, max_length=255)
    sort_order: int = Field(default=0, ge=0)


# ── Entries (objects) ─────────────────────────────────────────────────────────


class EntryPublic(BaseModel):
    id: uuid.UUID
    directory_id: uuid.UUID
    name: str
    avatar_path: str | None
    folder_url: str | None
    attributes: dict[str, str]
    note: str | None
    sort_order: int
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    contacts: list[ContactPublic] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class EntryList(BaseModel):
    items: list[EntryPublic]
    total: int
    limit: int
    offset: int


class CreateEntryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    folder_url: str | None = Field(default=None, max_length=2048)
    attributes: dict[str, str] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=1000)
    sort_order: int = Field(default=0, ge=0)
    contacts: list[ContactInput] = Field(default_factory=list)

    @field_validator("folder_url")
    @classmethod
    def validate_folder_url(cls, v: str | None) -> str | None:
        if v:
            return _validate_http_https_url(v)
        return v


class UpdateEntryRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    folder_url: str | None = Field(default=None, max_length=2048)
    attributes: dict[str, str] | None = None
    note: str | None = Field(default=None, max_length=1000)
    sort_order: int | None = Field(default=None, ge=0)
    contacts: list[ContactInput] | None = None

    @field_validator("folder_url")
    @classmethod
    def validate_folder_url(cls, v: str | None) -> str | None:
        if v:
            return _validate_http_https_url(v)
        return v
