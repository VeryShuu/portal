"""Helpdesk in-app notifications (Этап 4).

In-app уведомления через единый паттерн ``create_notification`` + Redis SSE
(см. ``app/services/notifications.py``). Email-часть (outbound через
``email_outbox``) — этап 5 (требует ``helpdesk_mailbox_settings`` и
``support_domain``); здесь только in-app.

Паттерн вызова (по образцу feedback): продюсер вызывается **после** commit
бизнес-операции, сам делает ``db.commit()`` (уведомления — best-effort, в
отдельной транзакции) и аккумулирует ``_publish``-колбэки для SSE после commit.
Получатели-агенты выбираются по ``helpdesk_agents`` JOIN ``users`` (а не по
``User.role``, как в feedback — агенты это отдельный список).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskAgent, HelpdeskTicket
from app.models.user import User
from app.services.notifications import create_notification

logger = get_logger(__name__)

_BATCH_SIZE = 500


async def _select_agents_to_notify(
    db: AsyncSession, *, exclude_user_id: uuid.UUID | None = None, require_notify_new: bool = True
) -> list[uuid.UUID]:
    """Все helpdesk-агенты (с живым аккаунтом и notify_inapp), опционально с
    ``notify_new=True``. JOIN users — единый источник правды о членстве."""
    conditions = [
        User.deleted_at.is_(None),
        User.notify_inapp.is_(True),
    ]
    if require_notify_new:
        conditions.append(HelpdeskAgent.notify_new.is_(True))
    q = (
        select(HelpdeskAgent.user_id)
        .join(User, User.id == HelpdeskAgent.user_id)
        .where(*conditions)
    )
    if exclude_user_id is not None:
        q = q.where(HelpdeskAgent.user_id != exclude_user_id)
    res = await db.execute(q)
    return list(res.scalars().all())


async def _fan_out(
    db: AsyncSession,
    redis: Redis,
    *,
    user_ids: list[uuid.UUID],
    type_: str,
    title: str,
    body: str | None,
    link: str | None,
) -> int:
    """Создать уведомления для списка получателей и опубликовать в SSE
    после commit (единый транзакционный batch)."""
    sent = 0
    publish_callbacks: list[Callable[[], Coroutine[Any, Any, None]]] = []
    for uid in user_ids:
        publish = await create_notification(
            db, redis, user_id=uid, type=type_, title=title, body=body, link=link
        )
        publish_callbacks.append(publish)
        sent += 1
    await db.commit()
    for publish in publish_callbacks:
        await publish()
    return sent


async def notify_ticket_created(db: AsyncSession, redis: Redis, *, ticket: HelpdeskTicket) -> int:
    """Новая заявка → уведомление всем агентам с ``notify_new=True``."""
    agent_ids = await _select_agents_to_notify(db, require_notify_new=True)
    sent = await _fan_out(
        db,
        redis,
        user_ids=agent_ids,
        type_="helpdesk_ticket_created",
        title=f"Новая заявка #{ticket.ticket_number}",
        body=ticket.subject,
        link=f"/helpdesk/tickets/{ticket.id}",
    )
    if sent:
        logger.info("helpdesk.notify_created_sent", ticket_id=str(ticket.id), sent=sent)
    return sent


async def notify_ticket_assigned(
    db: AsyncSession,
    redis: Redis,
    *,
    ticket: HelpdeskTicket,
    assignee: User,
    actor: User,
) -> int:
    """Взятие в работу / реассайн → инициатор + новый агент + старый агент
    (если был и отличается). Инициатору — in-app с ФИО ответственного."""
    targets: list[uuid.UUID] = []
    if ticket.requester_user_id is not None and ticket.requester_user_id != actor.id:
        targets.append(ticket.requester_user_id)
    if assignee.id != actor.id:
        targets.append(assignee.id)
    # Уведомление инициатору содержит ФИО ответственного (ТЗ §6).
    sent = await _fan_out(
        db,
        redis,
        user_ids=targets,
        type_="helpdesk_ticket_assigned",
        title=f"Заявка #{ticket.ticket_number} взята в работу",
        body=f"Ответственный: {assignee.full_name}.",
        link=f"/helpdesk/my/{ticket.id}",
    )
    return sent


async def notify_agent_reply(
    db: AsyncSession,
    redis: Redis,
    *,
    ticket: HelpdeskTicket,
    body_preview: str,
) -> int:
    """Публичный ответ агента → инициатору (это и есть «ответ»)."""
    targets: list[uuid.UUID] = []
    if ticket.requester_user_id is not None:
        targets.append(ticket.requester_user_id)
    return await _fan_out(
        db,
        redis,
        user_ids=targets,
        type_="helpdesk_agent_reply",
        title=f"Ответ по заявке #{ticket.ticket_number}",
        body=body_preview,
        link=f"/helpdesk/my/{ticket.id}",
    )


async def notify_requester_reply(
    db: AsyncSession,
    redis: Redis,
    *,
    ticket: HelpdeskTicket,
    body_preview: str,
) -> int:
    """Новое сообщение от клиента → текущему assignee (или всем агентам, если
    не назначен)."""
    if ticket.assignee_user_id is not None:
        targets = [ticket.assignee_user_id]
    else:
        targets = await _select_agents_to_notify(db, require_notify_new=False)
    return await _fan_out(
        db,
        redis,
        user_ids=targets,
        type_="helpdesk_requester_reply",
        title=f"Новое сообщение по заявке #{ticket.ticket_number}",
        body=body_preview,
        link=f"/helpdesk/tickets/{ticket.id}",
    )


async def notify_status_changed(
    db: AsyncSession,
    redis: Redis,
    *,
    ticket: HelpdeskTicket,
    new_status: str,
) -> int:
    """Статус → resolved/closed → инициатору (closed — с инфо о reopen-окне)."""
    from app.core.constants import HELPDESK_REOPEN_WINDOW_DAYS

    targets: list[uuid.UUID] = []
    if ticket.requester_user_id is not None:
        targets.append(ticket.requester_user_id)
    body = None
    if new_status == "closed":
        body = f"Ответить и переоткрыть можно в течение {HELPDESK_REOPEN_WINDOW_DAYS} дн."
    return await _fan_out(
        db,
        redis,
        user_ids=targets,
        type_="helpdesk_status_changed",
        title=f"Статус заявки #{ticket.ticket_number}: {new_status}",
        body=body,
        link=f"/helpdesk/my/{ticket.id}",
    )
