"""Pydantic-схемы модуля Directum (docs/directum.md).

Зеркалируют erp_sync-схемы; отличие — креды OData живут здесь (в erp_sync
IMAP вынесен в общие настройки email). Пароль write-only: в ответе только
``password_set: bool`` (паттерн ``MatrixBotSettingsOut.access_token_set``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Согласовано с CHECK-ограничением directum_runs.status (миграция 098).
RUN_STATUS_VALUES = ("success", "partial", "failed", "skipped")
TRIGGERED_BY_VALUES = ("cron", "manual")


# ── Settings (singleton) ────────────────────────────────────────────────────


class DirectumSettingsIn(BaseModel):
    """Настройки интеграции Directum.

    ``auth_password`` — write-only: пусто/None = оставить сохранённый шифр.
    При ``enabled=True`` обязателен полный набор кредов (существующий пароль
    или новый) — иначе PUT вернёт 400 (нельзя включить модуль без валидных
    кредов, паттерн matrix-бота).
    """

    enabled: bool = False
    base_url: str = Field(default="https://sed.mage.ru/Integration/odata", max_length=255)
    auth_username: str | None = Field(default=None, max_length=255)
    auth_password: str | None = Field(default=None, min_length=1, max_length=512)
    # Миграция 099: расписание задачи — часы запуска (московское время,
    # +03:00). Пустой список = авто-прогонов нет (только ручная кнопка).
    overdue_run_hours: list[int] = Field(default_factory=list, max_length=24)
    expected_interval_days: int = Field(ge=1, le=30, default=2)
    notify_emails: list[str] | None = Field(default=None, max_length=100)
    # Задача 1: «Просроченные задачи» — cron-гейтинг (manual-run обходит).
    overdue_enabled: bool = False

    @field_validator("overdue_run_hours")
    @classmethod
    def normalize_run_hours(cls, v: list[int]) -> list[int]:
        """Диапазон 0..23 (CHECK в БД), дубликаты убрать, сортировать."""
        for h in v:
            if not 0 <= h <= 23:
                raise ValueError("overdue_run_hours values must be between 0 and 23")
        return sorted(set(v))

    @field_validator("base_url")
    @classmethod
    def validate_base_url_scheme(cls, v: str) -> str:
        # scheme обязателен (как portal_base_url / matrix homeserver_url).
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("auth_username")
    @classmethod
    def strip_username(cls, v: str | None) -> str | None:
        # Логин вставляют копипастой — хвостовой пробел ломает basic auth.
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("auth_password")
    @classmethod
    def strip_password(cls, v: str | None) -> str | None:
        # Как токен matrix-бота: хвостовой пробел/перенос из копипасты доезжает
        # до Authorization-заголовка и даёт вводящую в заблуждение 401.
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("notify_emails")
    @classmethod
    def clean_notify_emails(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [e.strip() for e in v if e and e.strip()]
        return cleaned or None


class DirectumSettingsOut(BaseModel):
    """Текущие настройки; пароль скрыт (``password_set``), ``configured`` —
    производное «креды полные» (без учёта enabled)."""

    enabled: bool = False
    base_url: str = "https://sed.mage.ru/Integration/odata"
    auth_username: str | None = None
    password_set: bool = False
    configured: bool = False
    overdue_run_hours: list[int] = Field(default_factory=list)
    expected_interval_days: int = 2
    notify_emails: list[str] | None = None
    overdue_enabled: bool = False
    updated_at: datetime | None = None


# ── Runs (история прогонов) ─────────────────────────────────────────────────


class DirectumRunOut(BaseModel):
    """Один прогон. ``report`` (JSONB) возвращается как есть — фронтенд
    рендерит разделы notified / skipped_opt_in / unmatched / ambiguous."""

    id: int
    triggered_by: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    tasks_total: int | None = None
    performers_total: int | None = None
    users_notified: int | None = None
    users_skipped_opt_in: int | None = None
    users_unmatched: int | None = None
    users_ambiguous: int | None = None
    errors: int | None = None
    report: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}

    @field_validator("triggered_by")
    @classmethod
    def _validate_triggered_by(cls, v: str) -> str:
        if v not in TRIGGERED_BY_VALUES:
            raise ValueError(f"triggered_by must be one of {TRIGGERED_BY_VALUES}")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in RUN_STATUS_VALUES:
            raise ValueError(f"status must be one of {RUN_STATUS_VALUES}")
        return v


class DirectumRunList(BaseModel):
    """Пагинированный список прогонов (``GET /directum/runs``)."""

    items: list[DirectumRunOut]
    total: int


# ── Manual run (кнопка «Запустить сейчас») ──────────────────────────────────


class DirectumRunNowResponse(BaseModel):
    """Ответ ``POST /directum/run``: прогон поставлен в ARQ-очередь."""

    status: str = Field(description="queued (поставлен в ARQ-очередь)")
    job_id: str | None = None


# ── Connection test (кнопка «Проверить подключение») ────────────────────────


class DirectumTestResult(BaseModel):
    """Ответ ``POST /directum/test``: доступность OData + валидность кредов."""

    ok: bool
    error: str | None = None
    detail: str | None = None
