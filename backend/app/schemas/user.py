from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,63}$")

# Пол сотрудника — источником является ERP-выгрузка (миграция 087), но админ
# может отредактировать вручную. Значения фиксированы CHECK-ограничением БД.
GENDER_VALUES = ("male", "female")


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    department: str | None
    position: str | None
    phone: str | None
    role: str
    avatar_url: str | None
    presence_status: str
    lang: str
    created_at: datetime
    auth_source: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    last_login_at: datetime | None = None
    staff_sort_order: int | None = None
    staff_hidden: bool = False
    # ERP-синхронизация (миграция 087): видны всем авторизованным в карточке
    # /staff (аналогично position/phone).
    birth_date: date | None = None
    gender: str | None = None

    model_config = {"from_attributes": True}


class UserMe(UserPublic):
    notify_email: bool
    notify_inapp: bool
    preferences: dict[str, Any]
    last_login_at: datetime | None


class UserList(BaseModel):
    items: list[UserPublic]
    total: int


class BirthdayOut(BaseModel):
    """Именинник текущей недели для виджета на главной.

    Компактная схема (не весь ``UserPublic``): виджету нужны только ФИО, день
    рождения (для извлечения числа месяца) и аватар. ``birth_date`` — дата
    целиком (год не показываем, но он нужен для корректного 29 февраля)."""

    full_name: str
    birth_date: date
    avatar_url: str | None = None


class BirthdayList(BaseModel):
    items: list[BirthdayOut]
    total: int


class PatchProfileRequest(BaseModel):
    presence_status: str | None = None
    lang: str | None = None
    notify_email: bool | None = None
    notify_inapp: bool | None = None


class PatchPreferencesRequest(BaseModel):
    hidden_link_ids: list[str] | None = None
    onboarding_completed: bool | None = None
    onboarding_seen_step_ids: list[str] | None = Field(default=None, max_length=1000)


class PatchRoleRequest(BaseModel):
    role: str


class LocalLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v.lower()


class LocalUserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="reader")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v.lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("reader", "editor", "admin"):
            raise ValueError("role must be reader, editor or admin")
        return v


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminPatchProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = None
    position: str | None = None
    phone: str | None = None
    # ERP-синхронизация (миграция 087): ручное редактирование админом. Источник
    # истины — ERP, поэтому следующий импорт перетрёт эти значения, но до него
    # админ может скорректировать ошибку локально.
    birth_date: date | None = None
    gender: str | None = None

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is not None and v not in GENDER_VALUES:
            raise ValueError(f"gender must be one of {GENDER_VALUES}")
        return v


class DepartmentList(BaseModel):
    items: list[str]


class OfficeList(BaseModel):
    items: list[str]


class StaffOrderUserItem(BaseModel):
    id: uuid.UUID
    sort_order: int = Field(ge=0)


class StaffOrderUpdate(BaseModel):
    departments: list[str] = Field(default_factory=list)
    users: list[StaffOrderUserItem] = Field(default_factory=list)
    hidden_user_ids: list[uuid.UUID] = Field(default_factory=list)


class StaffOrderState(BaseModel):
    departments: list[str]
    hidden_user_ids: list[uuid.UUID]
