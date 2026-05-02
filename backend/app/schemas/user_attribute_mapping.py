import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserAttributeMappingPublic(BaseModel):
    id: uuid.UUID
    attr_key: str
    label_ru: str
    label_en: str | None
    sort_order: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserAttributeMappingSchema(BaseModel):
    """Public schema item used by the user profile page."""

    attr_key: str
    label_ru: str
    label_en: str | None = None
    sort_order: int = 0


class UserAttributeMappingSchemaList(BaseModel):
    items: list[UserAttributeMappingSchema]


class CreateUserAttributeMappingRequest(BaseModel):
    attr_key: str = Field(..., min_length=1, max_length=255)
    label_ru: str = Field(..., min_length=1, max_length=255)
    label_en: str | None = Field(default=None, max_length=255)
    sort_order: int = 0
    enabled: bool = True

    @field_validator("attr_key")
    @classmethod
    def _strip_key(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("attr_key required")
        return v


class UpdateUserAttributeMappingRequest(BaseModel):
    label_ru: str | None = Field(default=None, min_length=1, max_length=255)
    label_en: str | None = Field(default=None, max_length=255)
    sort_order: int | None = None
    enabled: bool | None = None


class DiscoverAttributeItem(BaseModel):
    attr_key: str
    sample: str | None = None
    occurrences: int


class DiscoverAttributesResponse(BaseModel):
    items: list[DiscoverAttributeItem]


class UserAttributeMappingList(BaseModel):
    items: list[UserAttributeMappingPublic]
    total: int
