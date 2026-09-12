"""SQLAlchemy-модели модуля интеграции с Directum (docs/directum.md).

Directum (СЭД) отдаёт данные по OData (``https://sed.mage.ru/Integration/odata``,
basic auth сервисной AD-учётки). Первая задача — «Просроченные задачи»: cron
запрашивает ``IAssignments`` (``Deadline lt NOW and Status eq 'InProcess'``),
группирует по исполнителю (ФИО), сопоставляет ФИО с ``users.full_name`` и шлёт
сотрудникам дайджест в личный чат Matrix (через ``messenger_outbox``,
opt-in ``chat_notifications_enabled``). После прогона — email-сводка админам.

Клон паттерна :mod:`app.models.erp_sync` (архитектурно модуль — «erp_sync с
HTTP-источником вместо IMAP»):

* :class:`DirectumSettings` — singleton (``id = 1``): общие настройки сверху,
  per-задачные — колонками с префиксом (``overdue_*``), как ``absences_*``.
* :class:`DirectumRun` — лог каждого прогона: счётчики + JSONB-отчёт
  (notified / skipped_opt_in / unmatched / ambiguous / matrix_disabled).
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


class DirectumSettings(Base):
    """Singleton row (``id = 1``) с настройками интеграции Directum.

    Пароль сервисной учётки — шифр Fernet (``auth_password_enc``, как
    ``matrix_bot_settings.access_token_enc``); plaintext write-only — API
    возвращает ``password_set: bool``.

    Гейтинг тройной (как erp_sync, но ``enabled`` здесь осмысленный):

    * ``modules.directum.enabled`` (в ``modules.json``) — мастер-переключатель
      всей фичи (API + cron + UI);
    * ``enabled`` (здесь, «Модуль включен») — гейтит и cron, и ручной запуск;
    * ``overdue_enabled`` — per-задачный переключатель задачи «Просроченные
      задачи» (только cron; ручной «Запустить сейчас» обходит, как
      ``poll_enabled`` в erp_sync).

    ``overdue_run_hours`` (миграция 099) — расписание задачи «Просроченные
    задачи»: часы запуска в московском времени (+03:00, как у Directum);
    пустой массив = авто-прогонов нет. Уведомляем **каждый прогон** (решение
    зафиксировано: расписание задаёт частоту напоминаний о висящих задачах).
    ``expected_interval_days`` — watchdog-порог «последний успех слишком старый».
    ``notify_emails`` — override получателей email-сводки (NULL = все админы
    с ``notify_email=true``).
    """

    __tablename__ = "directum_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_directum_settings_singleton"),
        # <@ («подмножество») — все элементы массива являются часами 0..23
        # (миграция 099; дубликаты/сортировку нормализует Pydantic-схема).
        CheckConstraint(
            "overdue_run_hours <@ ARRAY[0,1,2,3,4,5,6,7,8,9,10,11,"
            "12,13,14,15,16,17,18,19,20,21,22,23]",
            name="ck_directum_settings_run_hours",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE"), default=False
    )
    base_url: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("'https://sed.mage.ru/Integration/odata'"),
        default="https://sed.mage.ru/Integration/odata",
    )
    # Логин сервисной AD-учётки с доменом (например PDC1\portal-directum).
    auth_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Миграция 099: расписание задачи — часы запуска в московском времени
    # (+03:00, как у Directum). Пустой массив = авто-прогонов нет (только
    # ручная кнопка). Cron тикает ежечасно в :17 и сверяет текущий час MSK.
    overdue_run_hours: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'"), default=list
    )
    expected_interval_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("2"), default=2
    )
    notify_emails: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    # Задача 1: «Просроченные задачи» (IAssignments, Deadline lt NOW).
    overdue_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE"), default=False
    )
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


class DirectumRun(Base):
    """Один прогон синхронизации Directum (cron или ручной).

    Skip-причины (модуль выключен / интервал не прошёл / lock / креды не
    заданы) run-строку **не создают** — иначе cron-пол 5 минут заспамит
    историю; скип виден в логах воркера и в ответе задачи (``{"skipped": ...}``).

    ``status``:

    * ``success`` — выборка получена; все найденные исполнители обработаны
      (unmatched/ambiguous допустимы, это данные, а не сбой);
    * ``partial`` — часть сотрудников не уведомлена по технической причине
      (Matrix-бот не настроен);
    * ``failed`` — OData-запрос не выполнен (сеть/авторизация);
    * ``skipped`` — зарезервировано (прогон начат, но прерван до запроса).

    ``report`` — JSONB для email-сводки и раскрытия в админке: ``notified``
    (fio + mxid + tasks), ``skipped_opt_in`` (fio + tasks), ``unmatched`` (fio),
    ``ambiguous`` (fio + кандидаты), ``matrix_disabled: bool``, ``error`` (для
    failed). Списки обрезаны до 200 элементов (``truncated``-флаг), как в erp.
    """

    __tablename__ = "directum_runs"
    __table_args__ = (
        CheckConstraint("triggered_by IN ('cron', 'manual')", name="ck_directum_runs_triggered_by"),
        CheckConstraint(
            "status IN ('success', 'partial', 'failed', 'skipped')",
            name="ck_directum_runs_status",
        ),
        Index("ix_directum_runs_started_at", text("started_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    tasks_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    performers_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    users_notified: Mapped[int | None] = mapped_column(Integer, nullable=True)
    users_skipped_opt_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    users_unmatched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    users_ambiguous: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
