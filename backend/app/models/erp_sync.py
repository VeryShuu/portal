"""SQLAlchemy models for the ERP-sync module (docs/wip/erp-sync.md).

ERP (1С) присылает письмо 2×/неделю с отчётом «Справочник: Сотрудники»
(ФИО, дата рождения, пол). Портал опрашивает служебный ящик по IMAP (cron,
как helpdesk), парсит вложение, сопоставляет ФИО с ``users.full_name`` и
записывает ``birth_date`` + ``gender``. Каждый импорт перетирает значения;
diff попадает в email-отчёт админу.

Две таблицы:

* :class:`ErpSyncRun` — лог каждого импорта (idempotency по ``message_id`` для
  дедупа писем + JSONB-отчёт с разделами changed/unmatched/ambiguous/conflicts/
  errors).
* :class:`ErpSyncSettings` — singleton (``id = 1``) с IMAP-настройками ящика.
  Пароль — Fernet-шифр (как ``helpdesk_mailbox_settings.imap_password_enc``),
  plaintext write-only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ErpSyncRun(Base):
    """Один проход импорта ERP-выгрузки (автоматический по cron или ручной).

    ``message_id`` — для дедупа писем (UNIQUE): повторная обработка того же
    письма пропускается. ``NULL`` для ручного запуска (когда импорт
    инициирован админом без привязки к письму).

    ``report`` — JSONB со структурированным результатом для email-отчёта:
    ``changed`` (ФИО + поле old→new), ``unmatched`` (ФИО, нет в БД),
    ``ambiguous`` (ФИО → несколько кандидатов), ``conflicts`` (одно ФИО с
    разными датами/полом в файле), ``errors`` (невалидные строки).
    """

    __tablename__ = "erp_sync_runs"
    __table_args__ = (
        CheckConstraint("triggered_by IN ('cron', 'manual')", name="ck_erp_sync_runs_triggered_by"),
        CheckConstraint(
            "status IN ('success', 'partial', 'failed', 'skipped')",
            name="ck_erp_sync_runs_status",
        ),
        Index("ix_erp_sync_runs_started_at", text("started_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    attachment_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rows_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_matched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_unmatched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_ambiguous: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conflicts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )


class ErpSyncSettings(Base):
    """Singleton row (``id = 1``) с IMAP-настройками ящика, на который ERP шлёт
    отчёты. Клон паттерна ``helpdesk_mailbox_settings``.

    Пароль — шифр Fernet (``imap_password_enc``), plaintext write-only:
    API возвращает только ``imap_password_set: bool``.

    ``poll_interval_seconds`` (CHECK 60–3600) — как часто cron опрашивает ящик
    (по умолчанию 900 c = 15 мин). ``expected_interval_days`` — ожидаемый
    интервал между отчётами ERP (2×/неделю ≈ 4 дня); watchdog использует его
    для алерта «письма нет >N дней». ``notify_emails`` — override списка
    адресов для отчётов (NULL = все admin с ``notify_email=true``).
    """

    __tablename__ = "erp_sync_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_erp_sync_settings_singleton"),
        CheckConstraint(
            "poll_interval_seconds BETWEEN 60 AND 3600",
            name="ck_erp_sync_settings_poll_interval",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE"), default=False
    )
    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("993"))
    imap_use_ssl: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE"), default=True
    )
    imap_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    imap_folder: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'INBOX'"), default="INBOX"
    )
    poll_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("900"), default=900
    )
    expected_interval_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("4"), default=4
    )
    notify_emails: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(UTC),
    )

    updated_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[updated_by_user_id], lazy="select"
    )
