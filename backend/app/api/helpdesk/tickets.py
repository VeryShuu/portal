"""Requester-facing ticket endpoints (Helpdesk Этап 2).

Web-only flow для инициатора (reader/editor): создать заявку, посмотреть
свои, открыть свою с перепиской, ответить. ``internal``-сообщения и чужие
тикеты отсекаются (ACL «только свои», ТЗ §4.5). На этом этапе endpoints
принимают JSON без файлов — вложения появляются на этапе 4.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi_limiter.depends import RateLimiter

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.helpdesk._common import message_to_out, ticket_to_list_out, ticket_to_out
from app.schemas.helpdesk import (
    MessageCreateIn,
    MessageOut,
    TicketCreateIn,
    TicketListOut,
    TicketOut,
)
from app.services.helpdesk import messages as messages_service
from app.services.helpdesk import tickets as tickets_service

router = APIRouter(prefix="/helpdesk", tags=["helpdesk"])

# Допустимые значения ?status для list-эндпоинтов (ТЗ §3.1).
_TICKET_STATUSES = frozenset({"new", "open", "pending", "resolved", "closed"})


def _validate_status_filter(value: str | None) -> str | None:
    if value is not None and value not in _TICKET_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid status"
        )
    return value


@router.post(
    "/tickets",
    response_model=TicketOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заявку через веб-форму",
    dependencies=[Depends(RateLimiter(times=5, minutes=1))],
)
async def create_ticket(
    payload: TicketCreateIn,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,  # зарезервирован для этапа 4 (уведомления)
) -> TicketOut:
    ticket = await tickets_service.create_ticket(db, user=user, payload=payload)
    return ticket_to_out(ticket)


@router.get(
    "/tickets/my",
    response_model=TicketListOut,
    summary="Список своих заявок",
)
async def list_my_tickets(
    user: CurrentUser,
    db: DbDep,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TicketListOut:
    status_filter = _validate_status_filter(status_filter)
    total = await tickets_service.count_my_tickets(db, user_id=user.id, status_filter=status_filter)
    items = await tickets_service.list_my_tickets(
        db,
        user_id=user.id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return TicketListOut(
        items=[ticket_to_list_out(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tickets/my/{ticket_id}",
    response_model=TicketOut,
    summary="Своя заявка с публичными сообщениями",
)
async def get_my_ticket(
    ticket_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> TicketOut:
    # ACL: фильтр requester_user_id внутри запроса → чужой тикет = 404,
    # не раскрываем факт существования.
    ticket = await tickets_service.fetch_ticket_for_user(db, ticket_id=ticket_id, user_id=user.id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ticket_to_out(ticket)


@router.post(
    "/tickets/my/{ticket_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ответ по своей заявке",
    dependencies=[Depends(RateLimiter(times=20, minutes=1))],
)
async def add_my_message(
    ticket_id: uuid.UUID,
    payload: MessageCreateIn,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,  # зарезервирован для этапа 4 (уведомления)
) -> MessageOut:
    ticket = await tickets_service.fetch_ticket_for_user(db, ticket_id=ticket_id, user_id=user.id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    message = await messages_service.add_requester_reply(
        db, ticket=ticket, user=user, payload=payload
    )
    return message_to_out(message)
