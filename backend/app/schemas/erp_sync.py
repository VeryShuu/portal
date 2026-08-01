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
    """Per-module настройки ERP-sync. IMAP-приёмка общая (ADR-048, вкладка Email);

    здесь только переключатели, расписание, уведомления и фильтры писём
    (``mail_*_filter``), по которым модуль отбирает «свои» письма из общего ящика.
    """

    enabled: bool = False
    poll_interval_seconds: int = Field(ge=60, le=3600, default=900)
    expected_interval_days: int = Field(ge=1, le=30, default=4)
    notify_emails: list[str] | None = Field(default=None, max_length=100)
    # Миграция 088: двойной гейтинг поллинга + фильтрация писём на общем ящике.
    poll_enabled: bool = False
    mail_subject_filter: str | None = Field(default=None, max_length=255)
    mail_sender_filter: str | None = Field(default=None, max_length=255)
    mail_attachment_filter: str | None = Field(default=None, max_length=255)
    # Миграция 090: удалять письма из общего ящика после успешного импорта.
    delete_after_fetch: bool = False


class ErpSyncSettingsOut(BaseModel):
    """Текущие per-module настройки ERP-sync. IMAP живёт во вкладке Email."""

    enabled: bool = False
    poll_interval_seconds: int = 900
    expected_interval_days: int = 4
    notify_emails: list[str] | None = None
    poll_enabled: bool = False
    mail_subject_filter: str | None = None
    mail_sender_filter: str | None = None
    mail_attachment_filter: str | None = None
    delete_after_fetch: bool = False
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
