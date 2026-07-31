"""Pydantic schemas for the ERP-sync module (docs/wip/erp-sync.md).

Settings singleton — клон паттерна ``helpdesk``: пароль write-only (в ответе
только ``imap_password_set: bool``), ``configured=False`` означает, что
singleton-строка ещё не настроена (GET до первого PUT).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Согласовано с CHECK-ограничением erp_sync_runs.status (миграция 087).
RUN_STATUS_VALUES = ("success", "partial", "failed", "skipped")
TRIGGERED_BY_VALUES = ("cron", "manual")


# ── Settings (singleton) ────────────────────────────────────────────────────


class ErpSyncSettingsIn(BaseModel):
    """Конфиг ящика, на который ERP шлёт отчёты. ``imap_password`` — write-only:

    * при **создании** (первый ``PUT`` с ``enabled=true``) — обязателен;
    * при **обновлении** — опционален; ``None`` = «оставить прежний шифр».

    В отличие от helpdesk, IMAP-блок целиком nullable: модуль может быть
    выключен (``enabled=false``) с пустым ящиком, и только при включении
    требуется валидная конфигурация (проверяется в API-слое, не в схеме).
    """

    enabled: bool = False
    imap_host: str | None = Field(default=None, max_length=255)
    imap_port: int = Field(ge=1, le=65535, default=993)
    imap_use_ssl: bool = True
    imap_username: str | None = Field(default=None, max_length=255)
    imap_password: str | None = Field(default=None, min_length=1, max_length=512)
    imap_folder: str = Field(min_length=1, max_length=100, default="INBOX")
    poll_interval_seconds: int = Field(ge=60, le=3600, default=900)
    expected_interval_days: int = Field(ge=1, le=30, default=4)
    notify_emails: list[str] | None = Field(default=None, max_length=100)


class ErpSyncSettingsOut(BaseModel):
    """Текущие настройки. Пароль никогда не возвращается — только признак того,
    что он задан. ``configured`` здесь всегда ``True`` (singleton-строка
    создаётся миграцией 087 с defaults), поле оставлено для консистентности с
    ``HelpdeskMailboxSettingsOut``."""

    enabled: bool = False
    imap_host: str | None = None
    imap_port: int = 993
    imap_use_ssl: bool = True
    imap_username: str | None = None
    imap_password_set: bool = False
    imap_folder: str = "INBOX"
    poll_interval_seconds: int = 900
    expected_interval_days: int = 4
    notify_emails: list[str] | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Runs (история импортов) ─────────────────────────────────────────────────


class ErpSyncRunOut(BaseModel):
    """Один проход импорта. ``report`` (JSONB) возвращается как есть — фронтенд
    рендерит разделы changed/unmatched/ambiguous/conflicts/errors."""

    id: int
    message_id: str | None = None
    attachment_name: str | None = None
    triggered_by: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    rows_total: int | None = None
    rows_matched: int | None = None
    rows_updated: int | None = None
    rows_unmatched: int | None = None
    rows_ambiguous: int | None = None
    conflicts: int | None = None
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


class ErpSyncRunList(BaseModel):
    """Пагинированный список импортов (``GET /erp-sync/runs``)."""

    items: list[ErpSyncRunOut]
    total: int


# ── Manual run (кнопка «запустить синхронизацию») ───────────────────────────


class ErpSyncRunNowResponse(BaseModel):
    """Ответ ``POST /erp-sync/run``: запущен ли импорт сразу синхронно или
    поставлен в ARQ-очередь (``job_id``)."""

    status: str = Field(
        description="queued (поставлен в ARQ-очередь) | processed (выполнен синхронно)"
    )
    job_id: str | None = None
    run_id: int | None = None


class ErpSyncTestResult(BaseModel):
    """Результат проверки подключения к ящику (``POST /erp-sync/test``)."""

    ok: bool
    error: str | None = None
