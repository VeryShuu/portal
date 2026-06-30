"""Ticket lifecycle for the requester web-flow (Helpdesk Этап 2).

Создание тикета и списочное чтение «своих» тикетов. Инвариант первого
сообщения (ТЗ §4.3.1): при создании всегда создаётся первая запись в
``helpdesk_messages`` (``direction=inbound``, ``visibility=public``), а поля
``helpdesk_tickets.description`` дублируют её текст для быстрых списков и
поиска.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskTicket
from app.models.user import User
from app.schemas.helpdesk import TicketCreateIn

logger = get_logger(__name__)


async def create_ticket(
    db: AsyncSession,
    *,
    user: User,
    payload: TicketCreateIn,
) -> HelpdeskTicket:
    """Создать заявку от авторизованного пользователя (``source=web``).

    Транзакционно создаёт тикет и его первое public-inbound сообщение.
    ``requester_email``/``requester_name`` берутся из аккаунта пользователя —
    для web-flow гость не предусмотрен.
    """
    # Импорт here чтобы избежать цикла messages↔tickets на уровне модулей.
    from app.models.helpdesk import HelpdeskMessage

    ticket = HelpdeskTicket(
        subject=payload.subject,
        description=payload.description,
        status="new",
        source="web",
        requester_user_id=user.id,
        requester_email=user.email,
        requester_name=user.full_name,
    )
    db.add(ticket)
    await db.flush()  # нужен ticket.id + ticket.number перед созданием сообщения

    first_message = HelpdeskMessage(
        ticket_id=ticket.id,
        author_user_id=user.id,
        author_email=user.email,
        author_name=user.full_name,
        direction="inbound",
        visibility="public",
        body_text=payload.description,
        source="web",
    )
    db.add(first_message)

    await db.commit()
    await db.refresh(ticket)
    # Перечитываем с eager-load сообщений, чтобы возвращать полный объект.
    return await fetch_ticket_for_user(db, ticket_id=ticket.id, user_id=user.id)  # type: ignore[return-value]


async def count_my_tickets(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    status_filter: str | None,
) -> int:
    conditions = [HelpdeskTicket.requester_user_id == user_id]
    if status_filter:
        conditions.append(HelpdeskTicket.status == status_filter)
    res = await db.execute(select(func.count()).select_from(HelpdeskTicket).where(*conditions))
    return int(res.scalar_one())


async def list_my_tickets(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    status_filter: str | None,
    limit: int,
    offset: int,
) -> Sequence[HelpdeskTicket]:
    """Список тикетов инициатора. ``assignee_name`` подтягивается через
    relationship; для списков достаточно не загружать сообщения."""
    conditions = [HelpdeskTicket.requester_user_id == user_id]
    if status_filter:
        conditions.append(HelpdeskTicket.status == status_filter)
    res = await db.execute(
        select(HelpdeskTicket)
        .where(*conditions)
        .options(selectinload(HelpdeskTicket.assignee))
        .order_by(HelpdeskTicket.last_activity_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().unique().all()


async def fetch_ticket_for_user(
    db: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
) -> HelpdeskTicket | None:
    """Свой тикет с сообщениями. Фильтр по ``requester_user_id`` — основа ACL
    «только свои» (ТЗ §4.5); ``internal``-сообщения отсекаются на уровне
    сериализации (не здесь)."""
    res = await db.execute(
        select(HelpdeskTicket)
        .where(
            HelpdeskTicket.id == ticket_id,
            HelpdeskTicket.requester_user_id == user_id,
        )
        .options(
            selectinload(HelpdeskTicket.messages),
            selectinload(HelpdeskTicket.assignee),
        )
    )
    return res.scalars().unique().one_or_none()
