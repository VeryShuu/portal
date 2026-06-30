"""Adding messages to a ticket thread (Helpdesk Этап 2).

Ответ инициатора — всегда ``direction=inbound`` и ``visibility=public``
(внутренние заметки и outbound-ответы агентов появляются на этапе 3).
Согласно ТЗ §4.2.1, ответ клиента переводит тикет:

* ``pending`` → ``open`` (клиент «проснулся» — ждём агента);
* ``resolved`` → ``open`` без временного окна (ответ клиента = «не
  подтверждено»);
* ``new``/``open``/``closed`` остаются как есть на этом этапе (``closed``
  реопенится только агентом/админом или auto-reopen window — этап 3/5).

Во всех случаях обновляется ``last_activity_at``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket
from app.models.user import User
from app.schemas.helpdesk import MessageCreateIn

# Статусы, из которых ответ клиента реопенит тикет в ``open`` (ТЗ §4.2.1).
_REQUESTER_REOPEN_STATUSES = frozenset({"pending", "resolved"})


async def add_requester_reply(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    user: User,
    payload: MessageCreateIn,
) -> HelpdeskMessage:
    """Добавить ответ инициатора в свой тикет.

    ``ticket`` уже загружен и ACL-проверен роутером
    (``fetch_ticket_for_user``). Метод форсирует ``inbound``/``public``
    независимо от тела запроса — инициатор не может создать внутреннюю
    заметку или outbound-сообщение.
    """
    now = datetime.now(UTC)

    message = HelpdeskMessage(
        ticket_id=ticket.id,
        author_user_id=user.id,
        author_email=user.email,
        author_name=user.full_name,
        direction="inbound",
        visibility="public",
        body_text=payload.body_text,
        body_html=payload.body_html,
        source="web",
    )
    db.add(message)

    if ticket.status in _REQUESTER_REOPEN_STATUSES:
        ticket.status = "open"

    ticket.last_activity_at = now

    await db.commit()
    await db.refresh(message)
    return message


async def fetch_ticket_with_messages(
    db: AsyncSession, *, ticket_id: uuid.UUID
) -> HelpdeskTicket | None:
    """Загрузить тикет с сообщениями (используется роутером после добавления
    ответа для возврата обновлённого таймлайна)."""
    res = await db.execute(
        select(HelpdeskTicket)
        .where(HelpdeskTicket.id == ticket_id)
        .options(selectinload(HelpdeskTicket.messages))
    )
    return res.scalars().unique().one_or_none()
