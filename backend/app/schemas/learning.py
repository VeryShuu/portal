"""Pydantic-схемы модуля обучения (этап 1: учётки и аутентификация learner)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_EMAIL_MAX = 255


def _validate_email(value: str) -> str:
    # EmailStr не используем: DNS-проверка pydantic падает на .local-доменах
    # (gotcha из AGENTS.md). Минимальная структурная проверка — домен/формат
    # подтверждается отправкой письма.
    value = value.strip().lower()
    if "@" not in value or value.count("@") != 1:
        raise ValueError("Некорректный email")
    local, _, domain = value.partition("@")
    if not local or not domain or " " in value or len(domain.split(".")) < 2:
        raise ValueError("Некорректный email")
    return value


class LearningAccountCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=_EMAIL_MAX)
    full_name: str = Field(min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    position: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _validate_email(v)


class LearningAccountOut(BaseModel):
    """Представление учётки для админ-UI. Passwordless (миграция 113):
    парольных полей нет вовсе."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    department: str | None = None
    position: str | None = None
    status: str
    last_login_at: datetime | None = None
    created_at: datetime


class LearningAccountListOut(BaseModel):
    items: list[LearningAccountOut]
    total: int
    limit: int
    offset: int


class LearningAccountImportError(BaseModel):
    row: int = Field(ge=1)
    message: str


class LearningAccountImportOut(BaseModel):
    created: int = Field(ge=0)
    skipped_duplicates: int = Field(ge=0)
    error_count: int = Field(ge=0)
    errors: list[LearningAccountImportError]


class LearningLoginRequest(BaseModel):
    """Шаг 1 входа: запрос кода. Ответ всегда ``{"ok": true}`` — анти-enumeration."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=_EMAIL_MAX)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _validate_email(v)


class LearningVerifyRequest(BaseModel):
    """Шаг 2 входа: сверка кода из письма."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=_EMAIL_MAX)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _validate_email(v)


class LearningLoginCodeOut(BaseModel):
    """Ручная выдача кода админом (запасной путь «письмо не дошло»).
    Plaintext-код возвращается только здесь и только админу."""

    code: str
    expires_at: datetime


# ── Курсы (инкремент 2) ──────────────────────────────────────────────────────


class CourseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    slug: str | None = Field(default=None, max_length=140)
    # Категория курса (миграция 109): необязательная группировка на странице
    # «Обучение». Невалидный/soft-deleted id → 422 (сервис).
    category_id: uuid.UUID | None = None
    # Обязательный «для всех сотрудников» (миграция 111): курс автоматически
    # у каждого активного сотрудника, включая созданных позже.
    for_all_staff: bool = False
    # Опциональный срок прохождения (этап 2, §15): напоминание участникам — cron.
    deadline_at: datetime | None = None


class CourseUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    slug: str | None = Field(default=None, min_length=1, max_length=140)
    # Отсутствующий ключ = «не менять»; явный null = снять категорию.
    category_id: uuid.UUID | None = None
    # Наличие ключа в model_fields_set = применять (bool-поле, null невалиден).
    for_all_staff: bool | None = None
    # None = «не менять»; явная передача null (проверка model_fields_set в
    # роутере) = снять дедлайн.
    deadline_at: datetime | None = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    description: str | None = None
    status: str
    category_id: uuid.UUID | None = None
    for_all_staff: bool = False
    published_at: datetime | None = None
    created_at: datetime
    deadline_at: datetime | None = None
    # Путь превью и updated_at наружу не идут (exclude) — клиент получает
    # готовый cover_url с версионным ?v= для сброса кэша браузера.
    cover_path: str | None = Field(default=None, exclude=True)
    updated_at: datetime | None = Field(default=None, exclude=True)
    cover_url: str | None = None

    @model_validator(mode="after")
    def build_cover_url(self) -> CourseOut:
        if self.cover_path:
            v = int(self.updated_at.timestamp()) if self.updated_at else 0
            self.cover_url = f"/api/v1/learning/admin/courses/{self.id}/cover?v={v}"
        return self


class CourseListOut(BaseModel):
    items: list[CourseOut]
    total: int
    limit: int
    offset: int


def _check_url_scheme(v: str | None) -> str | None:
    if v is None:
        return v
    if not v.startswith(("http://", "https://")):
        raise ValueError("Схема ссылки должна быть http(s)")
    return v


class ItemCreate(BaseModel):
    """Материал: url опционален — PDF-файл прикладывается отдельным вызовом
    к созданному элементу (§6.2); тест: только заготовка элемента.
    description — rich-описание/комментарий материала (Markdown, sanitize
    на записи в сервисе, как у описания курса)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    type: str = Field(pattern="^(material|test|section)$")
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    url: str | None = Field(default=None, max_length=2048)
    file_path: str | None = Field(default=None, max_length=512)

    @field_validator("url")
    @classmethod
    def _url_scheme(cls, v: str | None) -> str | None:
        return _check_url_scheme(v)


class ItemUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    # Отсутствующий ключ = «не менять»; явный null = очистить описание.
    description: str | None = Field(default=None, max_length=8000)
    url: str | None = Field(default=None, max_length=2048)

    @field_validator("url")
    @classmethod
    def _url_scheme(cls, v: str | None) -> str | None:
        return _check_url_scheme(v)


class ItemsReorder(BaseModel):
    ordered_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    type: str
    title: str
    description: str | None = None
    sort_order: int
    url: str | None = None
    file_path: str | None = None


class CourseDetailOut(CourseOut):
    items: list[ItemOut] = []


class ParticipantEnroll(BaseModel):
    user_id: uuid.UUID | None = None
    learning_account_id: uuid.UUID | None = None


class ParticipantBulkEnroll(BaseModel):
    """Групповое зачисление сотрудников (этап 2, §15 «групповое зачисление
    выборкой»): дубли пропускаются, отчёт — в ответе."""

    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class ParticipantOut(BaseModel):
    id: uuid.UUID
    participant_kind: str  # 'staff' | 'external'
    display_name: str
    email: str | None = None
    enrolled_at: datetime
    progress_completed: int = 0
    progress_total: int = 0
    has_certificate: bool = False


class CourseProgressOut(BaseModel):
    course_id: uuid.UUID
    total_items: int
    participants: list[ParticipantOut]


class ParticipantItemStatusOut(BaseModel):
    """Строка детализации «как решён курс» у участника (методист)."""

    item_id: uuid.UUID
    title: str
    type: str  # 'material' | 'test'
    completed: bool
    test_passed: bool = False
    attempts_submitted: int = 0


class ParticipantItemsOut(BaseModel):
    participant_id: uuid.UUID
    items: list[ParticipantItemStatusOut]


class ParticipantAttemptsResetOut(BaseModel):
    ok: bool = True
    deleted_attempts: int


# ── Тесты и попытки (инкремент 3) ────────────────────────────────────────────


class TestSettingsUpdate(BaseModel):
    """Частичная правка настроек теста. max_attempts=0 — без ограничения
    попыток; pass_score в процентах (§6.3)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    pass_score: int | None = Field(default=None, ge=0, le=100)
    max_attempts: int | None = Field(default=None, ge=0, le=100)
    # Лимит времени попытки в минутах; отсутствует в теле = не менять,
    # явный null = снять ограничение (model_fields_set в роутере).
    time_limit_minutes: int | None = Field(default=None, ge=1, le=600)
    shuffle_questions: bool | None = None
    shuffle_answers: bool | None = None


class TestSettingsOut(BaseModel):
    pass_score: int
    max_attempts: int
    shuffle_questions: bool
    shuffle_answers: bool
    time_limit_minutes: int | None = None


class OptionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=2000)
    is_correct: bool = False
    sort_order: int = Field(default=0, ge=0)


class OptionOut(BaseModel):
    id: uuid.UUID
    text: str
    is_correct: bool
    sort_order: int


class QuestionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=8000)
    multi: bool = False
    options: list[OptionIn] = Field(min_length=2, max_length=12)

    @field_validator("options")
    @classmethod
    def _correct_options(cls, v: list[OptionIn]) -> list[OptionIn]:
        correct = sum(1 for o in v if o.is_correct)
        if correct == 0:
            raise ValueError("Нужен хотя бы один правильный вариант")
        return v


class QuestionOut(BaseModel):
    """Админское представление вопроса — с флагами правильности."""

    id: uuid.UUID
    text: str
    multi: bool
    sort_order: int
    options: list[OptionOut] = []


class ImportedQuestionIn(BaseModel):
    """Вопрос из xlsx-импорта (этап 2): шаблон фиксирует варианты A–D,
    поэтому верхний лимит вариантов жёстче, чем у ручного ввода."""

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=8000)
    multi: bool = False
    options: list[OptionIn] = Field(min_length=2, max_length=4)

    @field_validator("options")
    @classmethod
    def _correct_options(cls, v: list[OptionIn]) -> list[OptionIn]:
        correct = sum(1 for o in v if o.is_correct)
        if correct == 0:
            raise ValueError("Нужен хотя бы один правильный вариант")
        return v


class LearnerOptionOut(BaseModel):
    """Вариант участнику: без флага правильности (ТЗ §6.3)."""

    id: uuid.UUID
    text: str


class LearnerQuestionOut(BaseModel):
    id: uuid.UUID
    text: str
    multi: bool
    options: list[LearnerOptionOut] = []


class SubmitAnswers(BaseModel):
    answers: dict[uuid.UUID, list[uuid.UUID]]


class AttemptBrief(BaseModel):
    id: uuid.UUID
    status: str  # open | submitted | abandoned
    score: int | None = None
    passed: bool | None = None
    started_at: datetime
    submitted_at: datetime | None = None


class AttemptView(BaseModel):
    """Открытая попытка: вопросы в порядке снапшота, без ответов."""

    id: uuid.UUID
    status: str
    test_item_id: uuid.UUID
    questions: list[LearnerQuestionOut]
    max_attempts: int
    submitted_count: int
    remaining_attempts: int | None = None  # None = неограниченно (max_attempts=0)
    started_at: datetime
    # Таймер попытки (этап 2): лимит в минутах и абсолютный край
    # (started_at + лимит); None = ограничение не задано.
    time_limit_minutes: int | None = None
    expires_at: datetime | None = None


class AttemptResult(BaseModel):
    """Результат попытки: балл и статус; правильные ответы не раскрываются."""

    id: uuid.UUID
    status: str
    score: int | None = None
    passed: bool | None = None
    remaining_attempts: int | None = None
    started_at: datetime
    submitted_at: datetime | None = None


class MyAttemptsOut(BaseModel):
    test_item_id: uuid.UUID
    max_attempts: int
    submitted_count: int
    remaining_attempts: int | None = None
    attempts: list[AttemptBrief]


class MyCourseItemOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    description: str | None = None
    sort_order: int
    url: str | None = None
    has_file: bool = False
    completed: bool = False


class MyCourseOut(CourseOut):
    progress_completed: int = 0
    progress_total: int = 0
    # Денормализация категории для группировки на странице «Обучение»
    # (порядок блока — category_sort из справочника).
    category_title: str | None = None
    category_sort: int | None = None

    @model_validator(mode="after")
    def rebuild_cover_url(self) -> MyCourseOut:
        """Участнику обложка отдаётся через me-роут (проверка зачисления и
        публикации), поэтому админский URL из CourseOut перезаписывается
        (validators Pydantic v2 исполняются parent-first — итог здесь)."""
        if self.cover_path:
            v = int(self.updated_at.timestamp()) if self.updated_at else 0
            self.cover_url = f"/api/v1/learning/me/courses/{self.slug}/cover?v={v}"
        return self


class MyCourseDetailOut(MyCourseOut):
    items: list[MyCourseItemOut] = []


# ── методисты (learning_admins; назначает только глобальный админ, §3 ТЗ) ────


class LearningAdminCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: uuid.UUID


class LearningAdminOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    added_at: datetime


# ── мета модуля (обоим контурам: портал + learn; без секретов) ───────────────


class LearningMetaOut(BaseModel):
    """Публичные параметры модуля: origin'ы, iframe с которых разрешён.

    Источник — runtime-настройка ``system.json → video_iframe_origins``
    (Admin UI → System). Гейт плеера материалов и бейджа «видео» на обоих
    контурах; learn-сборка не имеет /bootstrap, поэтому читает их здесь.
    """

    video_iframe_origins: list[str] = []


# ── Категории курсов (справочник модуля; миграция 109) ───────────────────────


class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)


class CategoryOut(BaseModel):
    id: uuid.UUID
    title: str
    sort_order: int
    # Сколько активных курсов в категории (для UI справочника).
    course_count: int = 0


class CategoryReorder(BaseModel):
    ordered_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
