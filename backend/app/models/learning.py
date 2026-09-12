"""Модели модуля обучения (LMS) — этап 1 (ТЗ docs/wip/learning.md §7).

Два типа участников: сотрудники портала (``users``) и внешние учётки
(``learning_accounts``, вне Keycloak и вне штатного справочника). Принцип
двойного FK — ``user_id`` XOR ``learning_account_id`` (CHECK «ровно один»)
— повторяется во всех таблицах прогресса/зачисления.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# FK на сотрудников портала: users не софт-удаляются, но конвенция проекта —
# ON DELETE SET NULL (кроме membership-таблиц вроде helpdesk_agents/learning_admins,
# где строка без смысла без владельца → CASCADE).


class LearningAccount(Base):
    """Внешняя учётка обучаемого. Создаётся только методистом (§5.1 ТЗ)."""

    __tablename__ = "learning_accounts"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'blocked')", name="ck_learning_accounts_status"),
        # Уникальность email — case-insensitive среди активных (аналог
        # idx_users_email_ci_active из миграции 030/037).
        Index(
            "idx_learning_accounts_email_ci_active",
            sql_text("lower(email)"),
            unique=True,
            postgresql_where=sql_text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(255))
    # Passwordless-вход (миграции 113–114): паролей нет — вход по одноразовому
    # коду из письма (LearningLoginCode); парольные колонки дропнуты в 114.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningLoginCode(Base):
    """Одноразовый код входа (passwordless, миграция 113): email-запрос →
    письмо с 6-значным кодом → verify. Хранится только SHA-256 хэш; код живёт
    минуты, одноразовый (``used_at``), ``attempts`` считает неверные вводы —
    после лимита код мёртв, даже если ввели верно. Новый запрос кода
    инвалидирует предыдущие (единственный активный код на учётку)."""

    __tablename__ = "learning_login_codes"
    __table_args__ = (Index("ix_learning_login_codes_account", "account_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )


class LearningAdmin(Base):
    """Методист (= админ модуля). Единственная штатная роль модуля — паттерн
    helpdesk_agents; проверяется per-request зависимостью require_learning_admin."""

    __tablename__ = "learning_admins"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )


class LearningCourseCategory(Base):
    """Категория курсов («Инструктажи», «ГО и ЧС», …) — справочник модуля,
    управляет методист. Порядок — sort_order; soft-delete."""

    __tablename__ = "learning_course_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningCourse(Base):
    __tablename__ = "learning_courses"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published')", name="ck_learning_courses_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cover_path: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    # Категория курса (миграция 109): необязательная группировка на странице
    # «Обучение». SET NULL — категория не держит курс.
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_course_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Обязательный «для всех сотрудников» (миграция 111): доступ виртуальный
    # (любой активный сотрудник — участник, включая созданных позже); строки
    # участников материализуются при включении флага и в Keycloak-синке.
    for_all_staff: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("FALSE")
    )
    # Опциональный срок прохождения (этап 2, §15): напоминание — cron ARQ
    # за N суток (learning_deadline_reminder_days), одно на участника.
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningCourseItem(Base):
    """Элемент курса: материал (PDF-файл или ссылка) либо тест. Правило §15:
    тест, по которому есть попытки, правится только копией."""

    __tablename__ = "learning_course_items"
    __table_args__ = (
        CheckConstraint("type IN ('material', 'test', 'section')", name="ck_learning_items_type"),
        Index("idx_learning_items_course", "course_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Описание/комментарий материала (rich-text Markdown, sanitize на записи
    # через sanitize_markdown — как у описания курса; миграция 108).
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # material: либо файл, либо внешняя ссылка
    file_path: Mapped[str | None] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(String(2048))

    # Флаг «конфигурация теста использована попытками» (замок §15): ставится
    # tests_service._flag_test_config_used при попытках по тесту.
    test_config_used: Mapped[bool | None] = mapped_column(Boolean)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _participant_check(table: str) -> CheckConstraint:
    return CheckConstraint(
        "((user_id IS NOT NULL)::int + (learning_account_id IS NOT NULL)::int) = 1",
        name=f"ck_{table}_participant_xor",
    )


class LearningCourseParticipant(Base):
    """Зачисление участника на курс. Исключение — только soft-delete;
    попытки и прогресс остаются в истории (решение ревью 2026-08-26)."""

    __tablename__ = "learning_course_participants"
    __table_args__ = (
        _participant_check("learning_course_participants"),
        # Уникальность пары — частичными индексами: обычный UNIQUE с двумя
        # nullable-колонками пропускает дубли (NULL ≠ NULL в SQL).
        Index(
            "uq_learning_participants_user",
            "course_id",
            "user_id",
            unique=True,
            postgresql_where=sql_text("deleted_at IS NULL AND user_id IS NOT NULL"),
        ),
        Index(
            "uq_learning_participants_account",
            "course_id",
            "learning_account_id",
            unique=True,
            postgresql_where=sql_text("deleted_at IS NULL AND learning_account_id IS NOT NULL"),
        ),
        Index("idx_learning_participants_user", "user_id"),
        Index("idx_learning_participants_account", "learning_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    learning_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_accounts.id", ondelete="CASCADE")
    )
    enrolled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Снапшот личности на момент зачисления: отчёт прогресса и письма читают
    # его под ограниченной DB-ролью learning_app, которой SELECT users
    # недоступен по построению (§10.8, миграция 103).
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    # Напоминание о дедлайне отправлено (одно на участника курса, этап 2).
    deadline_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningTest(Base):
    """Настройки теста для элемента курса (1:1 c item)."""

    __tablename__ = "learning_tests"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_course_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pass_score: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # Лимит времени попытки в минутах (этап 2, §15); NULL = без ограничения.
    # Серверный контроль: submit после started_at + лимит → 409 + abandoned.
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer)
    shuffle_answers: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("FALSE"), default=False
    )
    shuffle_questions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("FALSE"), default=False
    )


class LearningQuestion(Base):
    __tablename__ = "learning_questions"
    __table_args__ = (Index("idx_learning_questions_test", "test_item_id", "sort_order"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    test_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_tests.item_id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    multi: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("FALSE"), default=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LearningQuestionOption(Base):
    __tablename__ = "learning_question_options"
    __table_args__ = (Index("idx_learning_options_question", "question_id", "sort_order"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("FALSE"), default=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LearningItemProgress(Base):
    """Отметка «ознакомлен» материала участником. % прохождения курса считается
    из этой таблицы + passed-попытки (ТЗ §7, ревью 2026-08-26)."""

    __tablename__ = "learning_item_progress"
    __table_args__ = (
        _participant_check("learning_item_progress"),
        Index(
            "uq_learning_progress_user",
            "item_id",
            "user_id",
            unique=True,
            postgresql_where=sql_text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_learning_progress_account",
            "item_id",
            "learning_account_id",
            unique=True,
            postgresql_where=sql_text("learning_account_id IS NOT NULL"),
        ),
        Index("idx_learning_progress_user", "user_id"),
        Index("idx_learning_progress_account", "learning_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_course_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    learning_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_accounts.id", ondelete="CASCADE")
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )


class LearningTestAttempt(Base):
    """Попытка прохождения теста. Лимит считается по отправленным (submitted);
    брошенная помечается abandoned_at через 24 часа (ТЗ §6.3). answers — снимок
    {question_id: [option_id, ...]}: правило неизменяемости теста (§15)."""

    __tablename__ = "learning_test_attempts"
    __table_args__ = (
        _participant_check("learning_test_attempts"),
        Index("idx_learning_attempts_test_submitted", "test_item_id", "submitted_at"),
        Index("idx_learning_attempts_user", "user_id"),
        Index("idx_learning_attempts_account", "learning_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    test_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_tests.item_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    learning_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_accounts.id", ondelete="CASCADE")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class LearningCertificate(Base):
    """Сертификат о прохождении курса (этап 2, ТЗ §15). Выдаётся один раз
    на участника курса; PDF живёт локально, путь канонический (проверяется
    при раздаче, как у материалов/обложек)."""

    __tablename__ = "learning_certificates"
    __table_args__ = (
        _participant_check("learning_certificates"),
        Index(
            "uq_learning_certificates_user",
            "course_id",
            "user_id",
            unique=True,
            postgresql_where=sql_text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_learning_certificates_account",
            "course_id",
            "learning_account_id",
            unique=True,
            postgresql_where=sql_text("learning_account_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    learning_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_accounts.id", ondelete="CASCADE")
    )
    # Короткий человекочитаемый номер документа (печатается на сертификате).
    serial: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    pdf_path: Mapped[str] = mapped_column(String(512), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
