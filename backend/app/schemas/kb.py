from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ── Авторы / пользователи (минимальное представление) ────────────────────────


class KbUserRef(BaseModel):
    id: uuid.UUID
    full_name: str
    avatar_url: str | None = None

    model_config = {"from_attributes": True}


# ── Теги ─────────────────────────────────────────────────────────────────────


class KbTagPublic(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


# ── Разделы ───────────────────────────────────────────────────────────────────


class KbSectionPublic(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    title: str
    slug: str
    description: str | None
    sort_order: int
    inherit_permissions: bool = True
    created_at: datetime
    user_permission: str | None = None
    children: list[KbSectionPublic] = Field(default_factory=list)

    model_config = {"from_attributes": True}


KbSectionPublic.model_rebuild()


class KbSectionList(BaseModel):
    items: list[KbSectionPublic]


class KbBreadcrumb(BaseModel):
    id: uuid.UUID
    title: str
    slug: str


class CreateSectionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)


class UpdateSectionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=0)


# ── Статьи ────────────────────────────────────────────────────────────────────


class KbArticleListItem(BaseModel):
    id: uuid.UUID
    title: str
    section_id: uuid.UUID | None
    status: str
    version: int
    view_count: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tags: list[KbTagPublic] = Field(default_factory=list)
    created_by: KbUserRef | None = None

    model_config = {"from_attributes": True}


class KbArticlePublic(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    section_id: uuid.UUID | None
    status: str
    version: int
    view_count: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tags: list[KbTagPublic] = Field(default_factory=list)
    breadcrumbs: list[KbBreadcrumb] = Field(default_factory=list)
    created_by: KbUserRef | None = None
    updated_by: KbUserRef | None = None
    helpful_count: int = 0
    not_helpful_count: int = 0
    user_feedback: bool | None = None
    inherit_permissions: bool = True
    user_permission: str | None = None

    model_config = {"from_attributes": True}


class KbArticleList(BaseModel):
    items: list[KbArticleListItem]
    total: int
    limit: int
    offset: int


class CreateArticleRequest(BaseModel):
    section_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="")
    status: str = Field(default="draft")
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("Too many tags (maximum 20)")
        for tag in v:
            if len(tag) > 100:
                raise ValueError("Tag name too long (maximum 100 characters)")
        return v


class UpdateArticleRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    section_id: uuid.UUID | None = None
    status: str | None = None
    tags: list[str] | None = None
    version: int = Field(..., description="Текущая версия статьи (оптимистичная блокировка)")
    change_comment: str | None = Field(default=None, max_length=500)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("Too many tags (maximum 20)")
        for tag in v:
            if len(tag) > 100:
                raise ValueError("Tag name too long (maximum 100 characters)")
        return v


class DraftSaveRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    version: int = Field(..., description="Текущая версия статьи (оптимистичная блокировка)")


# ── Версии ────────────────────────────────────────────────────────────────────


class KbVersionPublic(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    version: int
    title: str | None
    body: str | None
    change_comment: str | None
    changed_by: KbUserRef | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class KbVersionList(BaseModel):
    items: list[KbVersionPublic]
    total: int


# ── Комментарии ───────────────────────────────────────────────────────────────


class KbCommentPublic(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    body: str | None
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime
    author: KbUserRef | None = None

    model_config = {"from_attributes": True}


class KbCommentList(BaseModel):
    items: list[KbCommentPublic]
    total: int


class CreateCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


# ── Предложения правок ────────────────────────────────────────────────────────


class KbSuggestionPublic(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    body: str
    comment: str | None
    status: str
    reviewed_at: datetime | None
    created_at: datetime
    author: KbUserRef | None = None

    model_config = {"from_attributes": True}


class CreateSuggestionRequest(BaseModel):
    body: str = Field(min_length=1)
    comment: str | None = Field(default=None, max_length=500)


class ReviewSuggestionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")


class SuggestionResponse(BaseModel):
    suggestion_id: uuid.UUID
    message: str


class SuggestionListResponse(BaseModel):
    items: list[KbSuggestionPublic]


class ReviewSuggestionResponse(BaseModel):
    status: str


# ── Обратная связь ────────────────────────────────────────────────────────────


class FeedbackRequest(BaseModel):
    is_helpful: bool


class FeedbackStats(BaseModel):
    helpful_count: int
    not_helpful_count: int
    user_feedback: bool | None


# ── Поиск ─────────────────────────────────────────────────────────────────────


class SearchResultItem(BaseModel):
    type: str
    id: str
    title: str
    snippet: str | None = None
    url: str
    created_at: datetime | None = None
    author: str | None = None


class SearchResponse(BaseModel):
    items: list[SearchResultItem]
    total: int | None
    query: str


class SuggestResponse(BaseModel):
    suggestions: list[str]


# ── Корзина ───────────────────────────────────────────────────────────────────


class KbTrashItem(BaseModel):
    id: uuid.UUID
    title: str
    section_id: uuid.UUID | None
    section_title: str | None = None
    status: str
    deleted_at: datetime
    updated_at: datetime
    files_count: int = 0
    files_bytes: int = 0
    media_bytes: int = 0
    created_by: KbUserRef | None = None
    updated_by: KbUserRef | None = None


class KbTrashList(BaseModel):
    items: list[KbTrashItem]
    total: int
    retention_days: int
    purge_due_count: int


class KbTrashPurgeResult(BaseModel):
    purged: int
