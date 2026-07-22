"""Pydantic-схемы для модуля техподдержки (Helpdesk).

Контракты соответствуют ``docs/helpdesk.md`` (§4.3). Пароль IMAP —
write-only: в ответах возвращается только ``imap_password_set`` и
``configured`` (последнее — ``False``, пока singleton-строка настроек ещё не
создана первым ``PUT /settings/mailbox``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Pydantic EmailStr не работает с корпоративными .local-доменами (DNS-проверка).
# Для интранета используем обычную строку с ограничением длины — см. AGENTS.md.
type Email = str


class HelpdeskStatus(StrEnum):
    new = "new"
    open = "open"
    pending = "pending"
    closed = "closed"


class HelpdeskSource(StrEnum):
    email = "email"
    web = "web"


class HelpdeskDirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class HelpdeskVisibility(StrEnum):
    public = "public"
    internal = "internal"


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


class RequesterProfileOut(BaseModel):
    """Краткая «визитка» заявителя для отображения в карточке тикета.

    Собирается в рантайме из модели ``User`` (а не хранится в БД тикета) —
    профильные данные (отдел/должность/телефоны) меняются со временем, и в
    карточке всегда должна быть актуальная информация. Для гостевых заявок
    (нет аккаунта в портале) ищется сотрудник по ``email``; не найден →
    ``requester_profile=None`` (блок профиля не отрисовывается).
    """

    email: str
    full_name: str
    department: str | None = None
    position: str | None = None
    city: str | None = None
    mobile_phone: str | None = None
    internal_phone: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TicketCreateIn(BaseModel):
    """Web-форма создания заявки инициатором.

    ``description`` — plain-текст (для FTS, email plain-part, списков).
    ``description_html`` — HTML из rich-редактора (TipTap), опционально; при
    пустом ``description`` деривируется из HTML через ``html_to_plain``
    (симметрично ``MessageCreateIn.body_text``/``body_html``). Роутер
    санитизирует HTML (nh3) перед сохранением — заявитель неконтролируемая
    сторона, как email-ingress.
    """

    subject: str = Field(min_length=1, max_length=500)
    # ``min_length=0`` (не 1) — rich-редактор может прислать заявку, состоящую
    # только из картинки/таблицы без пояснительного plain-текста. Валидация
    # «хоть что-то есть» делается в роутере (plain ИЛИ html), симметрично
    # ``MessageCreateIn.body_text``.
    description: str = Field(min_length=0, max_length=20000)
    description_html: str | None = Field(default=None, max_length=50000)


class TicketAssignIn(BaseModel):
    assignee_user_id: uuid.UUID


class TicketStatusIn(BaseModel):
    """Ограниченный набор статусов, которые агент может выставить вручную.

    ``new`` и ``archived`` сюда не входят: ``new`` — стартовое состояние при
    создании, ``archived`` — это перенос в архивную таблицу, а не статус
    (см. ТЗ §1.3 п.9).
    """

    status: Literal["open", "pending", "closed"]


class TicketListItemOut(BaseModel):
    """Компактная карточка для списков (свои заявки / агентский инбокс)."""

    id: uuid.UUID
    number: int
    subject: str
    status: HelpdeskStatus
    source: HelpdeskSource
    requester_email: str
    requester_user_id: uuid.UUID | None = None
    requester_name: str | None = None
    assignee_user_id: uuid.UUID | None = None
    assignee_name: str | None = None
    last_activity_at: datetime
    created_at: datetime
    # Подсветка непрочитанных ответов заявителя для агента в инбоксе (миграция
    # 080). ``None`` (по умолчанию) — состояние неизвестно (не агентский путь,
    # например ``/tickets/my`` у заявителя, где unread-семантика другая).
    # ``True`` — есть публичные входящие сообщения новее ``last_seen_at`` агента.
    unread: bool | None = None

    model_config = ConfigDict(from_attributes=True)


class MarkTicketReadOut(BaseModel):
    """Ответ ``POST /tickets/{id}/read`` — подтверждение отметки «просмотрено»."""

    ok: bool = True
    ticket_id: uuid.UUID
    last_seen_at: datetime


class TicketOut(BaseModel):
    """Публичная карточка для инициатора (без internal-сообщений)."""

    id: uuid.UUID
    number: int
    subject: str
    description: str
    description_html: str | None = None
    status: HelpdeskStatus
    source: HelpdeskSource
    assignee_name: str | None = None
    requester_profile: RequesterProfileOut | None = None
    messages: list[MessageOut] = []
    last_activity_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketAgentOut(TicketOut):
    """Расширенная карточка для агентов/админов: видны internal-сообщения и
    служебные поля (assignee, closed_at, archived-reference)."""

    requester_user_id: uuid.UUID | None = None
    requester_email: str
    requester_name: str | None = None
    assignee_user_id: uuid.UUID | None = None
    assigned_at: datetime | None = None
    closed_at: datetime | None = None
    closed_by_user_id: uuid.UUID | None = None
    references_archived_ticket_number: int | None = None
    # Все участники тикета «в сборе» (миграция 083): requester + все Cc + все
    # авторы сообщений. Агрегируется в рантайме в ``ticket_to_agent_out`` (один
    # проход по сообщениям) — не хранится в БД. Источник для чекбокса «Ответить
    # всем» в форме ответа агента и для блока «Участники» в сайдбаре карточки.
    # Только агентский view (PII-минимизация: заявителю чужие Cc не показываем).
    participants: list[ParticipantOut] = []


class TicketListOut(BaseModel):
    items: list[TicketListItemOut]
    total: int
    limit: int
    offset: int


class TicketCountsOut(BaseModel):
    """Лёгкий ответ для счётчиков в меню. ``active`` — тикеты в статусах
    ``new``/``open``/``pending`` (закрытые исключены). Используется бейджем
    пункта меню: у заявителя — «мои открытые», у агента — «назначенные мне».
    Какие именно считать — определяется endpoint'ом (requester vs agent), здесь
    только форма ответа."""

    active: int


# ---------------------------------------------------------------------------
# Email participants (Cc) — миграция 083
# ---------------------------------------------------------------------------


class ParticipantOut(BaseModel):
    """Адресат письма: email + опциональное имя.

    Источник для inbound — заголовок ``Cc`` входящего письма (``extract_cc``);
    для outbound — форма ответа агента (чекбокс «Ответить всем»). В
    ``TicketAgentOut.participants`` поле ``is_requester`` отличает автора заявки
    от добавленных в копию (для подсветки в UI).
    """

    email: str
    name: str | None = None
    is_requester: bool = False


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class MessageCreateIn(BaseModel):
    """Тело ответа. ``visibility`` по умолчанию ``public`` (для инициатора
    доступен только этот путь); ``internal`` — заметка агента (не уходит на
    email, не видна инициатору).

    ``body_text`` допускает пустую строку — rich-редактор может прислать
    сообщение, состоящее только из картинки (``<img>`` без текста), и
    ``html_to_plain`` вернёт пустую строку. Валидация «хотя бы что-то есть»
    делается в роутере (plain ИЛИ html), а не на уровне схемы — иначе
    валидный image-only ответ получит 422.
    """

    body_text: str = Field(min_length=0, max_length=20000)
    body_html: str | None = Field(default=None, max_length=50000)
    visibility: HelpdeskVisibility = HelpdeskVisibility.public


class AttachmentOut(BaseModel):
    """Метаданные вложения сообщения. Сам файл отдаётся отдельным эндпоинтом
    ``GET /attachments/{id}`` (StreamingResponse); здесь — только данные для
    ссылки и иконки."""

    id: uuid.UUID
    filename: str
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    id: uuid.UUID
    direction: HelpdeskDirection
    visibility: HelpdeskVisibility
    source: HelpdeskSource
    author_email: str
    author_name: str | None = None
    author_user_id: uuid.UUID | None = None
    body_text: str
    body_html: str | None = None
    attachments: list[AttachmentOut] = []
    # Cc конкретного сообщения (миграция 083). Для inbound — из заголовка ``Cc``
    # входящего письма; для outbound — список, который агент указал при ответе.
    # ``None``/``[]`` для сообщений без копии (большинство). В UI показывается
    # компактным бейджем «Cc: a, b» под телом сообщения (только agent-mode).
    cc: list[ParticipantOut] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class AgentIn(BaseModel):
    user_id: uuid.UUID
    notify_new: bool = True


class AgentOut(BaseModel):
    user_id: uuid.UUID
    notify_new: bool
    added_at: datetime
    user_name: str | None = None
    user_email: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentListOut(BaseModel):
    items: list[AgentOut]
    total: int


class AgentOptionOut(BaseModel):
    """Компактный пункт списка смены ответственного: ``user_id`` + ФИО +
    email активного helpdesk-агента.

    В отличие от ``AgentOut``, не содержит флагов уведомлений (``notify_new``)
    и служебных меток — агенту для смены ответственного достаточно знать, кому
    можно передать заявку. PII-минимизация: только то, что нужно для списка.
    На фронте рендерится простым списком в popover (без поиска — агентов
    поддержки обычно ~5 человек).
    """

    user_id: uuid.UUID
    full_name: str | None = None
    email: str


class AgentOptionListOut(BaseModel):
    """Список активных агентов для смены ответственного в карточке тикета
    (агентский endpoint ``GET /tickets/assignable-agents``)."""

    items: list[AgentOptionOut]
    total: int


# ---------------------------------------------------------------------------
# Mailbox settings
# ---------------------------------------------------------------------------


class HelpdeskMailboxSettingsIn(BaseModel):
    """Конфиг support-mailbox. ``imap_password`` — write-only:

    * при **создании** записи (первый ``PUT``) — обязателен;
    * при **обновлении** — опционален; ``None`` = «оставить прежний шифр».
    """

    imap_host: str = Field(min_length=1, max_length=255)
    imap_port: int = Field(ge=1, le=65535, default=993)
    imap_username: str = Field(min_length=1, max_length=255)
    imap_password: str | None = Field(default=None, min_length=1, max_length=512)
    imap_use_ssl: bool = True
    imap_folder: str = Field(min_length=1, max_length=255, default="INBOX")
    poll_interval_seconds: int = Field(ge=30, le=600, default=60)
    delete_after_fetch: bool = False
    support_address: Email = Field(min_length=1, max_length=320)
    support_reply_to: Email | None = Field(default=None, max_length=320)


class HelpdeskMailboxSettingsOut(BaseModel):
    """Текущие настройки. Пароль никогда не возвращается — только признак того,
    что он задан. ``configured=False`` означает, что singleton-строка ещё не
    создана (GET до первого PUT — ТЗ §3.6)."""

    configured: bool = False
    imap_host: str | None = None
    imap_port: int = 993
    imap_username: str | None = None
    imap_password_set: bool = False
    imap_use_ssl: bool = True
    imap_folder: str = "INBOX"
    poll_interval_seconds: int = 60
    delete_after_fetch: bool = False
    support_address: str | None = None
    support_reply_to: str | None = None
    updated_at: datetime | None = None


# --- Daily digest settings -----------------------------------------------
# Singleton (id=1), seeded by migration 076. Unlike mailbox settings there is
# no "configured" state — the row always exists and ``enabled`` toggles sending.


class HelpdeskDigestSettingsIn(BaseModel):
    """Расписание ежедневной email-сводки по заявкам. ``digest_schedule``:
    ``weekdays`` — пн–пт, ``daily`` — каждый день. Время срабатывания —
    ``digest_hour:digest_minute`` (локальное UTC воркера)."""

    enabled: bool = True
    digest_hour: int = Field(ge=0, le=23, default=8)
    digest_minute: int = Field(ge=0, le=59, default=0)
    digest_schedule: Literal["weekdays", "daily"] = "weekdays"


class HelpdeskDigestSettingsOut(HelpdeskDigestSettingsIn):
    """Текущие настройки сводки. Строка засевается миграцией — ``updated_at``
    всегда заполнен (в отличие от mailbox-настроек, где GET до первого PUT
    возвращает ``configured=False``)."""

    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime | None = None


# --- MAX-messenger bot settings ---------------------------------------------
# Singleton (id=1), seeded by migration 081 with enabled=False. The admin
# flips ``enabled`` after entering ``bot_token`` (write-only) + ``chat_id`` of
# the common support chat. When enabled, every new helpdesk ticket produces a
# ``messenger_outbox`` entry that the cron worker dispatches to MAX Bot API.


class HelpdeskMaxBotSettingsIn(BaseModel):
    """Конфигурация MAX-бота для оповещений о новых заявках в чат поддержки.

    ``bot_token`` — write-only (как ``imap_password``): при обновлении ``None``
    = «оставить прежний шифр». Валидатор гарантирует, что при ``enabled=True``
    оба поля (токен на момент сохранения или уже сохранённый, и ``chat_id``)
    заполнены — иначе ``PUT`` вернёт 400.
    """

    enabled: bool = False
    bot_token: str | None = Field(default=None, min_length=1, max_length=512)
    chat_id: str | None = Field(default=None, min_length=1, max_length=64)


class HelpdeskMaxBotSettingsOut(BaseModel):
    """Текущие настройки MAX-бота. ``bot_token_set`` — признак, что токен задан
    (сам токен не возвращается). ``configured`` = ``enabled AND bot_token_set
    AND chat_id is not None`` — канал готов отправлять сообщения."""

    configured: bool = False
    enabled: bool = False
    bot_token_set: bool = False
    chat_id: str | None = None
    updated_at: datetime | None = None


class HelpdeskMaxBotTestResult(BaseModel):
    """Результат ``POST /max-bot/test``: дёргает MAX ``GET /me`` с текущим
    токеном, чтобы проверить, что бот валиден. ``detail`` на успехе — имя бота;
    ``error`` на неудаче замаскирован (defence-in-depth против утечки токена
    в HTTP-ответ/логи — полный traceback только в server-log через
    ``logger.exception``)."""

    ok: bool
    detail: str | None = None
    error: str | None = None


class HelpdeskUserOption(BaseModel):
    """Результат поиска пользователя для CC-селектора агента (``GET /users/search``).

    Используется блоком «Ответить всем»: агент ищет получателей копии по
    справочнику Keycloak (ФИО/email). ``email`` — ``str`` (не ``EmailStr``):
    Pydantic EmailStr ломается на корпоративных ``.local``-доменах (AGENTS.md
    gotcha), а валидацию формата Keycloak уже выполнил.
    """

    user_id: str
    full_name: str
    email: str
