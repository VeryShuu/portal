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
from app.schemas.helpdesk import (
    HelpdeskDirection,
    HelpdeskSource,
    HelpdeskStatus,
    HelpdeskVisibility,
    MessageOut,
    TicketListItemOut,
    TicketOut,
)

__all__ = ["message_to_out", "ticket_to_list_out", "ticket_to_out"]


def _public_messages(messages: list[HelpdeskMessage]) -> list[HelpdeskMessage]:
    """Только публичные сообщения (ACL-фильтр для инициатора)."""
    return [m for m in messages if m.visibility != HelpdeskVisibility.internal.value]


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
        created_at=msg.created_at,
    )


def _assignee_name(ticket: HelpdeskTicket) -> str | None:
    return ticket.assignee.full_name if ticket.assignee is not None else None


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
        messages=[message_to_out(m) for m in messages],
        last_activity_at=ticket.last_activity_at,
        created_at=ticket.created_at,
    )


def _is_owned_by(ticket: HelpdeskTicket | None, user_id: uuid.UUID) -> bool:
    return ticket is not None and ticket.requester_user_id == user_id
