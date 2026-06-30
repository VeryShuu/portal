"""Pydantic-схемы для модуля техподдержки (Helpdesk).

Контракты соответствуют ТЗ ``docs/wip/helpdesk.md`` (§4.3). Пароль IMAP —
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
    resolved = "resolved"
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


class HelpdeskEmailLogStatus(StrEnum):
    created = "created"
    appended = "appended"
    skipped = "skipped"
    error = "error"


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


class TicketCreateIn(BaseModel):
    """Web-форма создания заявки инициатором (без вложений до этапа 4)."""

    subject: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=20000)


class TicketAssignIn(BaseModel):
    assignee_user_id: uuid.UUID


class TicketStatusIn(BaseModel):
    """Ограниченный набор статусов, которые агент может выставить вручную.

    ``new`` и ``archived`` сюда не входят: ``new`` — стартовое состояние при
    создании, ``archived`` — это перенос в архивную таблицу, а не статус
    (см. ТЗ §1.3 п.9).
    """

    status: Literal["open", "pending", "resolved", "closed"]


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

    model_config = ConfigDict(from_attributes=True)


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


class TicketListOut(BaseModel):
    items: list[TicketListItemOut]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class MessageCreateIn(BaseModel):
    """Тело ответа. ``visibility`` по умолчанию ``public`` (для инициатора
    доступен только этот путь); ``internal`` — заметка агента (не уходит на
    email, не видна инициатору)."""

    body_text: str = Field(min_length=1, max_length=20000)
    body_html: str | None = Field(default=None, max_length=50000)
    visibility: HelpdeskVisibility = HelpdeskVisibility.public


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
