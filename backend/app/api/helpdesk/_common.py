"""Shared schema mappers for the helpdesk API package.

Сериализаторы отделяют «публичное» представление (для инициатора — без
``internal``-сообщений) от служебных полей. Здесь же — принципиальный
ACL-фильтр: сообщения c ``visibility='internal'`` никогда не попадают в
ответ инициатору (ТЗ §3.2, §4.5), даже если по какой-то причине оказались в
загруженной коллекции.
"""

from __future__ import annotations

import uuid

from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket
from app.models.user import User
from app.schemas.helpdesk import (
    AttachmentOut,
    HelpdeskDirection,
    HelpdeskSource,
    HelpdeskStatus,
    HelpdeskVisibility,
    MessageOut,
    RequesterProfileOut,
    TicketAgentOut,
    TicketListItemOut,
    TicketOut,
)

__all__ = [
    "build_requester_profile",
    "message_to_out",
    "ticket_to_agent_out",
    "ticket_to_list_out",
    "ticket_to_out",
]


def _public_messages(messages: list[HelpdeskMessage]) -> list[HelpdeskMessage]:
    """Только публичные сообщения (ACL-фильтр для инициатора)."""
    return [m for m in messages if m.visibility != HelpdeskVisibility.internal.value]


def _attachments(msg: HelpdeskMessage) -> list[AttachmentOut]:
    """Вложения сообщения. ``internal``-сообщения для инициатора уже
    отфильтрованы выше (``_public_messages``), поэтому здесь просто
    сериализуем то, что загружено через ``selectin`` relationship."""
    return [AttachmentOut.model_validate(a) for a in getattr(msg, "attachments", []) or []]


def message_to_out(msg: HelpdeskMessage) -> MessageOut:
    return MessageOut(
        id=msg.id,
        direction=HelpdeskDirection(msg.direction),
        visibility=HelpdeskVisibility(msg.visibility),
        source=HelpdeskSource(msg.source),
        author_email=msg.author_email,
        author_name=msg.author_name,
        author_user_id=msg.author_user_id,
        body_text=msg.body_text,
        body_html=msg.body_html,
        attachments=_attachments(msg),
        created_at=msg.created_at,
    )


def _assignee_name(ticket: HelpdeskTicket) -> str | None:
    return ticket.assignee.full_name if ticket.assignee is not None else None


def _attr_str(attributes: object, key: str) -> str | None:
    """Строковое значение из JSONB-``attributes`` пользователя (с type-гардом).

    ``city`` и ``mobile`` хранятся в ``users.attributes`` как строки (см.
    ``StaffCard.vue``/``staff_xlsx.py``). Любой не-строковый тип (число, null)
    игнорируется — берём только осмысленные строковые значения.
    """
    if not isinstance(attributes, dict):
        return None
    value = attributes.get(key)
    return value if isinstance(value, str) and value else None


def build_requester_profile(user: User | None) -> RequesterProfileOut | None:
    """Собрать краткий профиль заявителя из модели ``User``.

    Возвращает ``None``, если пользователь не передан (гостевая заявка без
    совпадения по email) — в этом случае блок профиля не отрисовывается.
    Поля ``city``/``mobile_phone`` берутся из JSONB ``attributes`` (ключи
    ``city``/``mobile``), ``internal_phone`` — из нативной колонки ``phone``.
    """
    if user is None:
        return None
    attrs = user.attributes or {}
    return RequesterProfileOut(
        email=user.email,
        full_name=user.full_name,
        department=user.department,
        position=user.position,
        city=_attr_str(attrs, "city"),
        mobile_phone=_attr_str(attrs, "mobile"),
        internal_phone=user.phone or None,
    )


def ticket_to_list_out(ticket: HelpdeskTicket) -> TicketListItemOut:
    return TicketListItemOut(
        id=ticket.id,
        number=ticket.number,
        subject=ticket.subject,
        status=HelpdeskStatus(ticket.status),
        source=HelpdeskSource(ticket.source),
        requester_email=ticket.requester_email,
        requester_user_id=ticket.requester_user_id,
        requester_name=ticket.requester_name,
        assignee_user_id=ticket.assignee_user_id,
        assignee_name=_assignee_name(ticket),
        last_activity_at=ticket.last_activity_at,
        created_at=ticket.created_at,
    )


def ticket_to_out(
    ticket: HelpdeskTicket,
    *,
    requester_view: bool = True,
    requester_profile: RequesterProfileOut | None = None,
) -> TicketOut:
    """Карточка тикета. При ``requester_view=True`` (по умолчанию) internal-сообщения
    отсекаются — это безопасный путь инициатора."""
    messages = _public_messages(ticket.messages) if requester_view else list(ticket.messages)
    return TicketOut(
        id=ticket.id,
        number=ticket.number,
        subject=ticket.subject,
        description=ticket.description,
        description_html=ticket.description_html,
        status=HelpdeskStatus(ticket.status),
        source=HelpdeskSource(ticket.source),
        assignee_name=_assignee_name(ticket),
        requester_profile=requester_profile,
        messages=[message_to_out(m) for m in messages],
        last_activity_at=ticket.last_activity_at,
        created_at=ticket.created_at,
    )


def _is_owned_by(ticket: HelpdeskTicket | None, user_id: uuid.UUID) -> bool:
    return ticket is not None and ticket.requester_user_id == user_id


def ticket_to_agent_out(
    ticket: HelpdeskTicket,
    *,
    requester_profile: RequesterProfileOut | None = None,
) -> TicketAgentOut:
    """Карточка для агентов/админов: видны все сообщения (включая internal)
    и служебные поля."""
    return TicketAgentOut(
        id=ticket.id,
        number=ticket.number,
        subject=ticket.subject,
        description=ticket.description,
        description_html=ticket.description_html,
        status=HelpdeskStatus(ticket.status),
        source=HelpdeskSource(ticket.source),
        assignee_name=_assignee_name(ticket),
        requester_profile=requester_profile,
        messages=[message_to_out(m) for m in ticket.messages],
        requester_user_id=ticket.requester_user_id,
        requester_email=ticket.requester_email,
        requester_name=ticket.requester_name,
        assignee_user_id=ticket.assignee_user_id,
        assigned_at=ticket.assigned_at,
        closed_at=ticket.closed_at,
        closed_by_user_id=ticket.closed_by_user_id,
        references_archived_ticket_number=ticket.references_archived_ticket_number,
        last_activity_at=ticket.last_activity_at,
        created_at=ticket.created_at,
    )
