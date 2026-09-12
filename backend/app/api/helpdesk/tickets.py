"""Ticket endpoints for the Helpdesk module (Этапы 2–3).

Две зоны прав:
* Инициатор (``CurrentUser``) — ``/tickets/my*`` и ``POST /tickets``. Чужие
  тикеты отсекаются (ACL «только свои»).
* Агент/админ (``HelpdeskAgentDep``) — ``/tickets``, ``/tickets/{id}`` и
  действия assign/take/status/reopen/message. Видят все сообщения.

Порядок объявления важен (ТЗ §4.4): сначала ``/tickets/my*``, затем
``/tickets`` (агентский list), затем ``/tickets/{id}``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import select

from app.api.deps import AdminDep, CurrentUser, DbDep, HelpdeskAgentDep, RedisDep
from app.api.helpdesk._common import (
    archived_ticket_to_agent_out,
    archived_ticket_to_list_out,
    archived_ticket_to_out,
    build_requester_profile,
    message_to_out,
    ticket_to_agent_out,
    ticket_to_list_out,
    ticket_to_out,
)
from app.api.kb._common import _rfc5987_filename
from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskAgent, HelpdeskTicket
from app.models.user import User
from app.schemas.helpdesk import (
    ALL_SOURCES,
    ALL_STATUSES,
    AgentOptionListOut,
    AgentOptionOut,
    CcRecipient,
    HelpdeskStatus,
    MarkTicketReadOut,
    MessageCreateIn,
    MessageOut,
    RequesterProfileOut,
    TicketAgentOut,
    TicketAssignIn,
    TicketCountsOut,
    TicketCreateIn,
    TicketListOut,
    TicketOut,
    TicketStatusIn,
)
from app.services.audit import push_audit_event
from app.services.helpdesk import archive as archive_service
from app.services.helpdesk import attachments as attachments_service
from app.services.helpdesk import messages as messages_service
from app.services.helpdesk import notifications as notifications_service
from app.services.helpdesk import outbound as outbound_service
from app.services.helpdesk import reads as reads_service
from app.services.helpdesk import tickets as tickets_service
from app.services.helpdesk.lifecycle import IllegalTransitionError

router = APIRouter(prefix="/helpdesk", tags=["helpdesk"])
logger = get_logger(__name__)


async def _try_notify(coro: Awaitable[object], *, context: str) -> None:
    """Best-effort in-app уведомление: сбой не должен ломать бизнес-операцию
    (паттерн feedback, ``feedback_service.create_feedback``)."""
    try:
        await coro
    except Exception as exc:
        logger.warning("helpdesk.notify_failed", context=context, error=str(exc))


# Допустимые значения ?status/?source для list-эндпоинтов (ТЗ §3.1).
# Берутся из enum'ов — единый источник истины (audit [H7]).
_TICKET_STATUSES = ALL_STATUSES
_TICKET_SOURCES = ALL_SOURCES


def _validate_status_filter(value: str | None) -> str | None:
    if value is not None and value not in _TICKET_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid status"
        )
    return value


# Разрешённые поля серверной сортировки списка заявок. Совпадает с whitelist
# в ``services/helpdesk/tickets.py::_apply_sort``. ``subject`` отсутствует — тема
# не сортируется (произвольный текст без естественного порядка).
_SORT_FIELDS = {"number", "status", "requester", "assignee", "created_at", "last_activity_at"}
_SORT_ORDERS = {"asc", "desc"}


def _sort_ticket_items(items: list, *, sort: str | None, order: str) -> list:
    """Sort the unified live+archived closed view before pagination.

    Closed tickets are bounded operational history rather than the active queue;
    we intentionally merge before slicing so archival cannot create gaps between
    pages. ``number`` is a deterministic tie-breaker.
    """
    key_map = {
        "number": lambda item: item.number,
        "status": lambda item: item.status.value,
        "requester": lambda item: (item.requester_name or item.requester_email).lower(),
        "assignee": lambda item: (item.assignee_name or "").lower(),
        "created_at": lambda item: item.created_at,
        "last_activity_at": lambda item: item.last_activity_at,
    }
    key = key_map.get(sort or "last_activity_at", key_map["last_activity_at"])
    return sorted(items, key=lambda item: (key(item), item.number), reverse=order == "desc")


async def _archive_assignee_names(
    db: DbDep, archived: list[archive_service.ArchivedTicket]
) -> dict[uuid.UUID | None, str]:
    ids = {item.row.assignee_user_id for item in archived if item.row.assignee_user_id is not None}
    if not ids:
        return {}
    from sqlalchemy import select

    rows = (await db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all()
    return {user_id: full_name for user_id, full_name in rows if full_name}


async def _closed_my_items(
    db: DbDep, *, user: CurrentUser, unassigned: bool, assigned: bool, sort: str | None, order: str
) -> list:
    # The archive view is intentionally a unified read model. Live closed tickets
    # remain visible during the grace period before the archive worker moves them.
    live = await tickets_service.list_my_tickets(
        db,
        user_id=user.id,
        status_filter="closed",
        limit=10_000,
        offset=0,
        unassigned=unassigned,
        assigned=assigned,
        sort=None,
        order=order,
    )
    archived = await archive_service.list_archived_tickets(
        db,
        requester_user_id=user.id,
        unassigned=unassigned,
        assigned=assigned,
    )
    names = await _archive_assignee_names(db, archived)
    archived_items = [
        archived_ticket_to_list_out(item, assignee_name=names.get(item.row.assignee_user_id))
        for item in archived
    ]
    return _sort_ticket_items(
        [ticket_to_list_out(item) for item in live] + archived_items,
        sort=sort,
        order=order,
    )


async def _closed_agent_items(
    db: DbDep,
    *,
    assignee: uuid.UUID | None,
    unassigned: bool,
    assigned: bool,
    source: str | None,
    query: str | None,
    sort: str | None,
    order: str,
) -> list:
    live = await tickets_service.list_agent_tickets(
        db,
        status_filter="closed",
        assignee_id=assignee,
        unassigned=unassigned,
        source=source,
        query=query,
        limit=10_000,
        offset=0,
        assigned=assigned,
        sort=None,
        order=order,
    )
    archived = await archive_service.list_archived_tickets(
        db,
        assignee_user_id=assignee,
        unassigned=unassigned,
        assigned=assigned,
        source=source,
        query=query,
    )
    names = await _archive_assignee_names(db, archived)
    archived_items = [
        archived_ticket_to_list_out(item, assignee_name=names.get(item.row.assignee_user_id))
        for item in archived
    ]
    return _sort_ticket_items(
        [ticket_to_list_out(item) for item in live] + archived_items,
        sort=sort,
        order=order,
    )


def _validate_sort(value: str | None) -> str | None:
    if value is not None and value not in _SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid sort field"
        )
    return value


def _validate_sort_order(value: str) -> str:
    if value not in _SORT_ORDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid order"
        )
    return value


def _validate_message_body(norm_text: str, norm_html: str | None) -> None:
    """Проверить, что сообщение содержит хоть какой-то контент.

    Валидно: есть plain-текст ИЛИ html-контент. Последнее нужно для rich-редактора:
    агент может отправить ответ, состоящий только из картинки (``<img>`` без
    пояснительного текста) — это нормальный кейс (скриншот ошибки без подписи).
    ``html_to_plain`` в таком случае возвращает пустую строку (тегов-то нет), и
    старая проверка ``if not norm_text`` отбрасывала валидный image-only ответ
    с 422. Теперь: если есть html (после sanitize) — сообщение принято, даже
    когда plain пустой.
    """
    if not norm_text and not norm_html:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Message body is empty",
        )


# Лимит адресатов в копии (защита от злоупотребления / ошибочного «ответить
# всем» по 500-адресному рассылочному письму). 20 — достаточно для реальных
# рабочих групп; превышение → 422 с понятным сообщением.
HELPDESK_CC_MAX_RECIPIENTS = 20


def _normalize_cc_emails(
    cc_raw: list[str],
    *,
    exclude: set[str],
    support_address: str | None,
) -> list[CcRecipient]:
    """Нормализовать список Cc-адресов из Form-поля в ``list[CcRecipient]``.

    Операции:
    * ``strip``/``lower`` каждого адреса; пропуск пустых и без ``@``;
    * дедупликация (по lowercased email);
    * отсечение ``exclude`` (email агента — он уже в ``From``; ``requester_email``
      — он уже в ``To``, не дублируем в Cc) и ``support_address`` (петля — см.
      ``extract_cc``);
    * ``name`` — ``None`` (агент вводит голые email'ы через ``n-select``; имя
      резолвится на стороне получателя по его адресной книге).

    Лимит ``HELPDESK_CC_MAX_RECIPIENTS`` → 422 (явная ошибка, не молчаливое
    обрезание — агент должен видеть, что список слишком большой).

    Возвращает типизированный ``list[CcRecipient]`` (audit [L10]) — Pydantic
    ловит typo в ключах на границе Producer → JSONB-storage → Consumer.
    """
    if not cc_raw:
        return []
    exclude_lc = {e.strip().lower() for e in exclude if e}
    if support_address:
        exclude_lc.add(support_address.strip().lower())

    result: list[CcRecipient] = []
    seen: set[str] = set()
    for entry in cc_raw:
        # Form-поле может прийти как "Иван <a@x>" или голый "a@x". Берём адрес.
        email = entry.strip().lower()
        if "<" in email and ">" in email:
            inner = email.rsplit("<", 1)[-1].split(">", 1)[0].strip()
            email = inner
        if not email or "@" not in email:
            continue
        if email in exclude_lc or email in seen:
            continue
        seen.add(email)
        result.append(CcRecipient(email=email, name=None))

    if len(result) > HELPDESK_CC_MAX_RECIPIENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Too many Cc recipients (max {HELPDESK_CC_MAX_RECIPIENTS})",
        )
    return result


@router.post(
    "/tickets",
    response_model=TicketOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заявку через веб-форму (multipart/form-data)",
    dependencies=[Depends(RateLimiter(times=5, minutes=1))],
)
async def create_ticket(
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    subject: str = Form(..., min_length=1, max_length=500),
    # ``description`` optional с деривацией из ``description_html`` (симметрично
    # ``add_my_message``/``add_agent_message``): rich-редактор TipTap шлёт HTML,
    # plain бэк деривирует сам. Старые клиенты (только plain) работают как прежде.
    description: str = Form(default="", max_length=20000),
    description_html: str = Form(default="", max_length=50000),
    files: list[UploadFile] = File(default=[]),
) -> TicketOut:
    # Нормализация для rich-редактора: sanitize description_html (nh3) + деривация
    # description (plain) для FTS/email-треда, если фронт прислал только HTML.
    norm_text: str
    norm_html: str | None
    norm_text, norm_html = messages_service.normalize_message_bodies(description, description_html)
    _validate_message_body(norm_text, norm_html)
    payload = TicketCreateIn(subject=subject, description=norm_text, description_html=norm_html)
    ticket = await tickets_service.create_ticket(db, user=user, payload=payload, files=files)
    # Первое сообщение тикета (тело заявки для письма агентам). ``create_ticket``
    # возвращает тикет с загруженными сообщениями (``fetch_ticket_for_user``);
    # по инварианту первого сообщения список непуст и отсортирован по created_at.
    first_message = ticket.messages[0] if ticket.messages else None
    await _try_notify(
        notifications_service.notify_ticket_created(db, redis, ticket=ticket),
        context="ticket_created",
    )
    # Email-уведомление агентам о новой заявке (best-effort, через outbox
    # ``kind=generic`` — не требует настроенного mailbox, работает в web-only).
    if first_message is not None:
        await _try_notify(
            notifications_service.notify_ticket_created_email(
                db, ticket=ticket, first_message=first_message
            ),
            context="ticket_created_email",
        )
        # MAX-messenger уведомление в общий чат поддержки (best-effort, через
        # ``messenger_outbox``). Только при включённом канале (см.
        # HelpdeskMaxBotSettings.enabled) — иначе функция делает no-op.
        await _try_notify(
            notifications_service.notify_ticket_created_max(
                db, ticket=ticket, first_message=first_message
            ),
            context="ticket_created_max",
        )
    return ticket_to_out(ticket, requester_profile=build_requester_profile(user))


@router.get(
    "/tickets/my",
    response_model=TicketListOut,
    summary="Список своих заявок",
)
async def list_my_tickets(
    user: CurrentUser,
    db: DbDep,
    status_filter: str | None = Query(default=None, alias="status"),
    unassigned: bool = Query(default=False),
    assigned: bool = Query(default=False),
    active_only: bool = Query(default=False),
    sort: str | None = Query(default=None),
    order: str = Query(default="desc"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TicketListOut:
    status_filter = _validate_status_filter(status_filter)
    sort = _validate_sort(sort)
    order = _validate_sort_order(order)
    if status_filter == HelpdeskStatus.closed:
        all_items = await _closed_my_items(
            db, user=user, unassigned=unassigned, assigned=assigned, sort=sort, order=order
        )
        return TicketListOut(
            items=all_items[offset : offset + limit],
            total=len(all_items),
            limit=limit,
            offset=offset,
        )
    total = await tickets_service.count_my_tickets(
        db,
        user_id=user.id,
        status_filter=status_filter,
        unassigned=unassigned,
        assigned=assigned,
        active_only=active_only,
    )
    items = await tickets_service.list_my_tickets(
        db,
        user_id=user.id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
        unassigned=unassigned,
        assigned=assigned,
        active_only=active_only,
        sort=sort,
        order=order,
    )
    # Unread для заявителя: «есть ли публичные ответы агентов новее last_seen_at».
    # Контракт зеркален агентскому (там — ответы заявителя, direction='inbound'),
    # здесь — direction='outbound'. Один запрос на весь список (защита от N+1).
    unread_map = await reads_service.enrich_with_unread(
        db, tickets=items, user_id=user.id, direction=reads_service.OUTBOUND_DIRECTION
    )
    return TicketListOut(
        items=[ticket_to_list_out(i, unread=unread_map.get(i.id)) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tickets/my/counts",
    response_model=TicketCountsOut,
    summary="Счётчик своих открытых заявок (для бейджа в меню)",
)
async def get_my_ticket_counts(
    user: CurrentUser,
    db: DbDep,
) -> TicketCountsOut:
    """Лёгкий count-endpoint для бейджа в меню пункта «Поддержка».

    ``active`` — свои тикеты в статусах new/open/pending (closed исключён как
    архивная история). Один ``count(*)`` без join'ов и пагинации — дешевле
    list-endpoint'а с ``limit=1``, особенно при polling'е раз в 60 c.

    ``unread`` — сколько из активных имеют непрочитанные ответы агентов
    (``direction='outbound'``, зеркало агентского счётчика): фронт красит
    цифру бейджа в красный при ``unread > 0``.
    """
    active = await tickets_service.count_my_active_tickets(db, user_id=user.id)
    unread = await reads_service.count_my_unread_tickets(db, user_id=user.id)
    return TicketCountsOut(active=active, unread=unread)


@router.post(
    "/tickets/my/{ticket_id}/read",
    response_model=MarkTicketReadOut,
    summary="Отметить свой тикет прочитанным (снять подсветку ответов агентов)",
)
async def mark_my_ticket_read(
    ticket_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> MarkTicketReadOut:
    """Заявительский аналог ``POST /tickets/{id}/read`` (агентского).

    Записывает ``last_seen_at = NOW()`` для пары ``(ticket, user)`` — UPSERT по
    ``uq_helpdesk_ticket_reads_ticket_user``. Снимает подсветку в списке своих
    заявок: после открытия карточки заявителем ответы агентов больше не
    подсвечиваются как непрочитанные (контракт ``direction='outbound'`` в
    ``enrich_with_unread``, см. ``GET /tickets/my``).

    ACL: только свои тикеты (``fetch_ticket_for_user`` → 404 для чужих, не
    раскрываем существование). Не требует audit/rate-limit (read-state —
    бизнес-состояние, как ``notifications.read``). Идемпотентно.
    """
    ticket = await tickets_service.fetch_ticket_for_user(db, ticket_id=ticket_id, user_id=user.id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    seen_at = await reads_service.mark_ticket_seen(db, ticket_id=ticket_id, user_id=user.id)
    await db.commit()
    return MarkTicketReadOut(ticket_id=ticket_id, last_seen_at=seen_at)


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
    if ticket is not None:
        return ticket_to_out(ticket, requester_profile=build_requester_profile(user))
    archived = await archive_service.fetch_archived_ticket(db, ticket_id=ticket_id)
    if archived is None or archived.row.requester_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    assignee_names = await _archive_assignee_names(db, [archived])
    return archived_ticket_to_out(
        archived,
        requester_profile=build_requester_profile(user),
        assignee_name=assignee_names.get(archived.row.assignee_user_id),
    )


@router.post(
    "/tickets/my/{ticket_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ответ по своей заявке",
    dependencies=[Depends(RateLimiter(times=20, minutes=1))],
)
async def add_my_message(
    ticket_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    body_text: str = Form(default="", max_length=20000),
    body_html: str = Form(default="", max_length=50000),
    files: list[UploadFile] = File(default=[]),
) -> MessageOut:
    ticket = await tickets_service.fetch_ticket_for_user(db, ticket_id=ticket_id, user_id=user.id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    # Нормализация для rich-редактора: sanitize body_html (nh3) + деривация
    # body_text (plain) для email-треда, если фронт прислал только HTML.
    norm_text: str
    norm_html: str | None
    norm_text, norm_html = messages_service.normalize_message_bodies(body_text, body_html)
    _validate_message_body(norm_text, norm_html)
    payload = MessageCreateIn(body_text=norm_text, body_html=norm_html)
    message = await messages_service.add_requester_reply(
        db, ticket=ticket, user=user, payload=payload, files=files
    )
    await _try_notify(
        notifications_service.notify_requester_reply(
            db, redis, ticket=ticket, body_preview=message.body_text
        ),
        context="requester_reply",
    )
    # Email-уведомление агенту о новом сообщении от заявителя (best-effort,
    # через outbox ``kind=generic`` — симметрично in-app выше). Как
    # ``notify_ticket_created_email`` при создании заявки: отдельный канал,
    # сбой не роняет бизнес-операцию.
    await _try_notify(
        notifications_service.notify_requester_reply_email(db, ticket=ticket, message=message),
        context="requester_reply_email",
    )
    return message_to_out(message)


# ===========================================================================
# Agent zone (Этап 3)
# ===========================================================================


def _validate_source(value: str | None) -> str | None:
    if value is not None and value not in _TICKET_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid source"
        )
    return value


def _illegal_to_409(exc: IllegalTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "current_status": exc.current,
            "allowed": exc.allowed,
            "message": "Illegal status transition",
        },
    )


async def _load_agent_ticket(
    db: DbDep, ticket_id: uuid.UUID, *, for_update: bool = False
) -> HelpdeskTicket:
    ticket = await tickets_service.fetch_ticket_for_agent(
        db, ticket_id=ticket_id, for_update=for_update
    )
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ticket


def _require_ticket_owner(ticket: HelpdeskTicket, *, actor: User) -> None:
    """Блокировка мутаций за назначенным агентом (assignee-lock).

    Правило «одна заявка — один исполнитель»: если на тикете назначен агент,
    работу с ним (комментарий, смена статуса, reopen) ведёт только он. Остальные
    агенты обязаны сначала сменить ответственного на себя через ``POST /assign``
    (или ``/take`` для неназначенной заявки). Админ подчиняется тому же правилу
    — без admin-bypass, исключений нет.

    Неназначенный тикет (``assignee_user_id IS NULL``) пропускается: любой
    агент может взять его в работу (``take`` или первым ответом через
    авто-назначение в ``messages.add_agent_reply``).
    """
    if ticket.assignee_user_id is not None and ticket.assignee_user_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Ticket is assigned to another agent",
                "assignee_user_id": str(ticket.assignee_user_id),
            },
        )


async def _ticket_requester_profile(
    db: DbDep, *, ticket: HelpdeskTicket
) -> RequesterProfileOut | None:
    """Профиль заявителя для карточки агента. Для гостевых email-заявок —
    fallback-поиск сотрудника по email; не найден → ``None`` (блок скрыт)."""
    requester = await tickets_service.resolve_requester_user(db, ticket=ticket)
    return build_requester_profile(requester)


# Email-продюсеры (outbox) вынесены в ``app.services.helpdesk.outbound``
# (AGENTS.md: бизнес-логика — в сервисах, роутер — тонкий wiring-слой).


@router.get(
    "/tickets",
    response_model=TicketListOut,
    summary="Все заявки (агентский инбокс)",
)
async def list_all_tickets(
    agent: HelpdeskAgentDep,
    db: DbDep,
    status_filter: str | None = Query(default=None, alias="status"),
    assignee: uuid.UUID | None = Query(default=None),
    unassigned: bool = Query(default=False),
    source: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    assigned: bool = Query(default=False),
    q: str | None = Query(default=None, min_length=0, max_length=200),
    sort: str | None = Query(default=None),
    order: str = Query(default="desc"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TicketListOut:
    status_filter = _validate_status_filter(status_filter)
    source = _validate_source(source)
    sort = _validate_sort(sort)
    order = _validate_sort_order(order)
    if status_filter == HelpdeskStatus.closed:
        all_items = await _closed_agent_items(
            db,
            assignee=assignee,
            unassigned=unassigned,
            assigned=assigned,
            source=source,
            query=q,
            sort=sort,
            order=order,
        )
        return TicketListOut(
            items=all_items[offset : offset + limit],
            total=len(all_items),
            limit=limit,
            offset=offset,
        )
    total = await tickets_service.count_agent_tickets(
        db,
        status_filter=status_filter,
        assignee_id=assignee,
        unassigned=unassigned,
        source=source,
        query=q,
        active_only=active_only,
        assigned=assigned,
    )
    items = await tickets_service.list_agent_tickets(
        db,
        status_filter=status_filter,
        assignee_id=assignee,
        unassigned=unassigned,
        source=source,
        query=q,
        limit=limit,
        offset=offset,
        active_only=active_only,
        assigned=assigned,
        sort=sort,
        order=order,
    )
    # Enrich одним запросом: какие тикеты имеют непрочитанные ответы заявителя
    # для этого агента (миграция 080). Без этого был бы N+1 — на каждый тикет
    # отдельный EXISTS-запрос. Map → O(1)-lookup в сериализаторе.
    unread_map = await reads_service.enrich_with_unread(db, tickets=items, user_id=agent.id)
    return TicketListOut(
        items=[ticket_to_list_out(i, unread=unread_map.get(i.id)) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tickets/counts",
    response_model=TicketCountsOut,
    summary="Счётчик назначенных агенту тикетов в работе (для бейджа в меню)",
)
async def get_agent_ticket_counts(
    agent: HelpdeskAgentDep,
    db: DbDep,
) -> TicketCountsOut:
    """Лёгкий count-endpoint для бейджа в меню пункта «Инбокс поддержки».

    ``active`` — тикеты, назначенные лично этому агенту (``assignee = agent``),
    в статусах new/open/pending. «Моя нагрузка», а не «объём очереди»:
    неназначенные тикеты здесь не считаются (для них есть отдельный блок в
    инбоксе). ``closed`` исключён. Один ``count(*)`` без join'ов.

    ``unread`` — сколько из активных назначенных имеют непрочитанные ответы
    заявителя (миграция 080, семантика reads-сервиса): фронт красит цифру
    бейджа в красный при ``unread > 0``.
    """
    active = await tickets_service.count_assigned_active_tickets(db, user_id=agent.id)
    unread = await reads_service.count_unread_assigned_tickets(db, user_id=agent.id)
    return TicketCountsOut(active=active, unread=unread)


@router.get(
    "/tickets/assignable-agents",
    response_model=AgentOptionListOut,
    summary="Активные агенты для смены ответственного (список)",
)
async def list_assignable_agents(
    agent: HelpdeskAgentDep,
    db: DbDep,
) -> AgentOptionListOut:
    """Все активные helpdesk-агенты (с живым аккаунтом, ``deleted_at IS NULL``)
    для списка смены ответственного в карточке тикета.

    Возвращает компактные пункты ``(user_id, full_name, email)`` без флагов
    уведомлений (PII-минимизация: агенту для смены ответственного достаточно
    знать, кому можно передать заявку). Сортировка — по ФИО. На фронте
    рендерится простым списком в popover (без поиска — агентов поддержки
    обычно ~5 человек).

    Доступ — любой helpdesk-агент/админ (``HelpdeskAgentDep``): смена
    ответственного доступна любому агенту, а не только админу. Не заменяет
    admin-only ``GET /agents`` (там есть флаги ``notify_new`` и
    admin-управление составом), а даёт агентам минимум данных для операции.
    """
    rows = await tickets_service.list_assignable_agents(db)
    items = [
        AgentOptionOut(user_id=uid, full_name=full_name, email=email)
        for uid, full_name, email in rows
    ]
    return AgentOptionListOut(items=items, total=len(items))


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketAgentOut,
    summary="Карточка заявки (агентский view, все сообщения)",
)
async def get_ticket(
    ticket_id: uuid.UUID,
    agent: HelpdeskAgentDep,
    db: DbDep,
) -> TicketAgentOut:
    ticket = await tickets_service.fetch_ticket_for_agent(db, ticket_id=ticket_id)
    if ticket is not None:
        profile = await _ticket_requester_profile(db, ticket=ticket)
        return ticket_to_agent_out(ticket, requester_profile=profile)
    archived = await archive_service.fetch_archived_ticket(db, ticket_id=ticket_id)
    if archived is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    requester = await archive_service.resolve_archived_requester_user(db, ticket=archived)
    assignee_names = await _archive_assignee_names(db, [archived])
    return archived_ticket_to_agent_out(
        archived,
        requester_profile=build_requester_profile(requester),
        assignee_name=assignee_names.get(archived.row.assignee_user_id),
    )


@router.post(
    "/tickets/{ticket_id}/read",
    response_model=MarkTicketReadOut,
    summary="Отметить тикет прочитанным (снять подсветку в инбоксе агента)",
)
async def mark_ticket_read(
    ticket_id: uuid.UUID,
    agent: HelpdeskAgentDep,
    db: DbDep,
) -> MarkTicketReadOut:
    """Записать ``last_seen_at = NOW()`` для пары ``(ticket, agent)`` — UPSERT
    по ``uq_helpdesk_ticket_reads_ticket_user``. Вызывается фронтендом при
    открытии карточки тикета (точка «прочитано» в инбоксе агента).

    Не требует audit (read-state — бизнес-состояние, не мутация, как
    ``notifications.read``) и rate-limit (доступ только HelpdeskAgentDep).
    Идемпотентно: повторное открытие карточки = более свежий ``last_seen_at``.
    """
    # Проверка существования тикета + агентский ACL (404 если нет/нет доступа).
    await _load_agent_ticket(db, ticket_id)
    seen_at = await reads_service.mark_ticket_seen(db, ticket_id=ticket_id, user_id=agent.id)
    await db.commit()
    return MarkTicketReadOut(ticket_id=ticket_id, last_seen_at=seen_at)


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ответ агента",
)
async def add_agent_message(
    ticket_id: uuid.UUID,
    agent: HelpdeskAgentDep,
    db: DbDep,
    redis: RedisDep,
    body_text: str = Form(default="", max_length=20000),
    body_html: str = Form(default="", max_length=50000),
    # Cc — повторяющееся Form-поле (``cc=a@x&cc=b@y``), опциональное. Агент
    # включает «Ответить всем» → фронт шлёт список email'ов участников. Лимит
    # 20 — защита от злоупотребления; ``_normalize_cc_emails`` ниже выкидывает
    # support_address (петля) и email самого агента.
    cc: list[str] = Form(default=[]),
    files: list[UploadFile] = File(default=[]),
) -> MessageOut:
    ticket = await _load_agent_ticket(db, ticket_id, for_update=True)
    _require_ticket_owner(ticket, actor=agent)
    # Нормализация для rich-редактора: sanitize body_html (nh3) + деривация
    # body_text (plain) для email-треда, если агент прислал только HTML.
    norm_text: str
    norm_html: str | None
    norm_text, norm_html = messages_service.normalize_message_bodies(body_text, body_html)
    _validate_message_body(norm_text, norm_html)
    payload = MessageCreateIn(
        body_text=norm_text,
        body_html=norm_html,
    )
    # Mailbox settings: нужен support_domain для генерации Message-ID и
    # формирования исходящего письма. Mailbox может быть не настроен — тогда
    # ответ создаётся, но email не отправляется (только in-app).
    mailbox = await outbound_service.load_mailbox(db)
    support_domain = outbound_service.support_domain(mailbox)
    # Cc нормализуется здесь (а не в сервисе): валидация — ответственность
    # роутера (как ``_validate_message_body``). Сервис ``add_agent_reply``
    # получает уже чистый список ``[{email, name}]``. ``support_address`` и
    # email агента выкидываем (петля / дублирование To).
    cc_normalized = _normalize_cc_emails(
        cc,
        exclude={agent.email, ticket.requester_email},
        support_address=mailbox.support_address if mailbox else None,
    )
    message = await messages_service.add_agent_reply(
        db,
        ticket=ticket,
        agent=agent,
        payload=payload,
        files=files,
        support_domain=support_domain,
        cc=cc_normalized or None,
    )
    if (
        # Outbox email (только если mailbox сконфигурирован) — ставится в ту же
        # транзакцию, что и ответ (outbox-инвариант AGENTS.md). Сбой enqueue
        # откатывает ответ (агент видит 500, повторяет) — это сознательно: иначе
        # письмо заявителю терялось при сохранённом ответе. Не best-effort.
        mailbox is not None and support_domain and message.email_message_id
    ):
        await outbound_service.enqueue_reply_outbound(
            db, ticket=ticket, message=message, mailbox=mailbox
        )
    # Единый commit: ответ агента + outbox-запись (если есть) — атомарно.
    await db.commit()
    await _try_notify(
        notifications_service.notify_agent_reply(
            db, redis, ticket=ticket, body_preview=message.body_text
        ),
        context="agent_reply",
    )
    await push_audit_event(
        redis,
        event_type="helpdesk.message_added",
        user_id=str(agent.id),
        user_email=agent.email,
        resource_type="helpdesk_ticket",
        resource_id=str(ticket.id),
        metadata={"direction": message.direction},
    )
    return message_to_out(message)


@router.post(
    "/tickets/{ticket_id}/assign",
    response_model=TicketAgentOut,
    summary="Назначить ответственного",
)
async def assign_ticket(
    ticket_id: uuid.UUID,
    payload: TicketAssignIn,
    agent: HelpdeskAgentDep,
    db: DbDep,
    redis: RedisDep,
) -> TicketAgentOut:
    ticket = await _load_agent_ticket(db, ticket_id, for_update=True)
    # Валидация таргета: передать заявку можно только действующему
    # helpdesk-агенту (требование: «сменить на любого агента тех. поддержки»).
    # Не-агент / удалённый аккаунт → 404 (не раскрываем детали членства).
    # 404 (а не 400/422) — единый ответ «not found» для пользовательского id,
    # как и в других lookup-эндпоинтах helpdesk (см. ``_load_agent_ticket``).
    if not await tickets_service.is_active_helpdesk_agent(db, user_id=payload.assignee_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    # Реассайн: запоминаем предыдущего assignee ДО смены, чтобы пометить в audit
    # (отличить take от реассайна в логах). ``took=True`` ставится только в
    # ``take_ticket`` (взятие на себя неназначенной заявки), здесь всегда
    # ``reassigned=True`` — даже если заявка до этого не была никому назначена,
    # действие шло от агента, выбирающего другого исполнителя.
    previous_assignee_id = ticket.assignee_user_id
    ticket = await tickets_service.assign_ticket(
        db, ticket=ticket, assignee_id=payload.assignee_user_id
    )
    assignee = await outbound_service.load_user(db, payload.assignee_user_id)
    # Email инициатору с ФИО ответственного (ТЗ §6) — только при
    # сконфигурированном mailbox. Ставится в ту же транзакцию, что и назначение
    # (outbox-инвариант AGENTS.md). Сбой enqueue откатывает назначение — это
    # сознательно: иначе письмо терялось при сохранённом назначении.
    if assignee is not None:
        mailbox = await outbound_service.load_mailbox(db)
        if mailbox is not None and outbound_service.support_domain(mailbox):
            await outbound_service.enqueue_assigned_email(
                db, ticket=ticket, assignee=assignee, actor=agent, mailbox=mailbox
            )
    # Единый commit: назначение + outbox-запись (если есть) — атомарно.
    await db.commit()
    if assignee is not None:
        await _try_notify(
            notifications_service.notify_ticket_assigned(
                db, redis, ticket=ticket, assignee=assignee, actor=agent
            ),
            context="ticket_assigned",
        )
    await push_audit_event(
        redis,
        event_type="helpdesk.assigned",
        user_id=str(agent.id),
        user_email=agent.email,
        resource_type="helpdesk_ticket",
        resource_id=str(ticket.id),
        metadata={
            "assignee_user_id": str(payload.assignee_user_id),
            # ``reassigned=True`` отличает смену ответственного от первичного
            # назначения через ``take`` в audit-логе (полезно для отчётов).
            "reassigned": previous_assignee_id is not None,
            **(
                {"previous_assignee_user_id": str(previous_assignee_id)}
                if previous_assignee_id is not None
                else {}
            ),
        },
    )
    profile = await _ticket_requester_profile(db, ticket=ticket)
    return ticket_to_agent_out(ticket, requester_profile=profile)


@router.post(
    "/tickets/{ticket_id}/take",
    response_model=TicketAgentOut,
    summary="Взять нераспределённую заявку на себя",
)
async def take_ticket(
    ticket_id: uuid.UUID,
    agent: HelpdeskAgentDep,
    db: DbDep,
    redis: RedisDep,
) -> TicketAgentOut:
    # Транзакционное ядро (lock → check → assign → outbox → commit) —
    # в production-сервисе; его же драйвит integration-тест (audit-review
    # 2026-08-22, P1).
    ticket = await tickets_service.take_ticket_tx(db, ticket_id=ticket_id, agent=agent)
    await _try_notify(
        notifications_service.notify_ticket_assigned(
            db, redis, ticket=ticket, assignee=agent, actor=agent
        ),
        context="ticket_taken",
    )
    await push_audit_event(
        redis,
        event_type="helpdesk.assigned",
        user_id=str(agent.id),
        user_email=agent.email,
        resource_type="helpdesk_ticket",
        resource_id=str(ticket.id),
        metadata={"assignee_user_id": str(agent.id), "took": True},
    )
    profile = await _ticket_requester_profile(db, ticket=ticket)
    return ticket_to_agent_out(ticket, requester_profile=profile)


@router.patch(
    "/tickets/{ticket_id}/status",
    response_model=TicketAgentOut,
    summary="Сменить статус по машине состояний",
)
async def change_ticket_status(
    ticket_id: uuid.UUID,
    payload: TicketStatusIn,
    agent: HelpdeskAgentDep,
    db: DbDep,
    redis: RedisDep,
) -> TicketAgentOut:
    ticket = await _load_agent_ticket(db, ticket_id)
    _require_ticket_owner(ticket, actor=agent)
    try:
        ticket = await tickets_service.change_status(
            db, ticket=ticket, target=payload.status, actor=agent
        )
    except IllegalTransitionError as exc:
        raise _illegal_to_409(exc) from None
    if payload.status == HelpdeskStatus.closed:
        await _try_notify(
            notifications_service.notify_status_changed(
                db, redis, ticket=ticket, new_status=payload.status
            ),
            context="status_changed",
        )
    await push_audit_event(
        redis,
        event_type="helpdesk.status_changed",
        user_id=str(agent.id),
        user_email=agent.email,
        resource_type="helpdesk_ticket",
        resource_id=str(ticket.id),
        metadata={"status": payload.status},
    )
    profile = await _ticket_requester_profile(db, ticket=ticket)
    return ticket_to_agent_out(ticket, requester_profile=profile)


@router.post(
    "/tickets/{ticket_id}/reopen",
    response_model=TicketAgentOut,
    summary="Reopen закрытой заявки",
)
async def reopen_ticket(
    ticket_id: uuid.UUID,
    agent: HelpdeskAgentDep,
    db: DbDep,
    redis: RedisDep,
) -> TicketAgentOut:
    ticket = await _load_agent_ticket(db, ticket_id)
    _require_ticket_owner(ticket, actor=agent)
    try:
        ticket = await tickets_service.reopen_ticket(db, ticket=ticket)
    except IllegalTransitionError as exc:
        raise _illegal_to_409(exc) from None
    await push_audit_event(
        redis,
        event_type="helpdesk.status_changed",
        user_id=str(agent.id),
        user_email=agent.email,
        resource_type="helpdesk_ticket",
        resource_id=str(ticket.id),
        metadata={"reopened": True},
    )
    profile = await _ticket_requester_profile(db, ticket=ticket)
    return ticket_to_agent_out(ticket, requester_profile=profile)


@router.delete(
    "/tickets/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Полностью удалить заявку (только администратор)",
)
async def delete_ticket(
    ticket_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    """Hard-delete тикета со всеми данными (БД + файлы диска).

    **Только администратор** (``AdminDep`` — строго ``role == "admin"``, иначе
    403). Не доступно агентам поддержки и заявителю — это необратимая операция
    (спам-очистка / GDPR-удаление), в отличие от ``close``/``reopen`` которые
    делает агент.

    Удаляет (через ``services.helpdesk.tickets.delete_ticket`` + CASCADE в БД):
    * строку ``helpdesk_tickets``;
    * каскадно — сообщения, вложения (записи), marker-reads;
    * файлы вложений и inline-картинок на диске (``delete_ticket_dir``,
      best-effort).

    Не трогает архив и не шлёт уведомлений — тихое удаление, фиксируется только
    в журнале аудита как ``helpdesk.ticket_deleted``. Возвращает ``204`` без
    тела. Несуществующий ``ticket_id`` → ``404`` (через ``_load_agent_ticket``,
    единый loader с агентскими эндпоинтами — не раскрывает существование).
    """
    # Переиспользуем агентский loader (404 на отсутствие/нет доступа). loader
    # требует HelpdeskAgentDep, но админ — суперсет агента (require_helpdesk_agent
    # пропускает admin), а сам SELECT по id без ACL-фильтра — для admin'а это
    # безопасно (он видит все тикеты). Не вызываем через зависимость, т.к.
    # эндпоинт уже gated AdminDep сверху.
    ticket = await _load_agent_ticket(db, ticket_id)
    number = await tickets_service.delete_ticket(db, ticket=ticket)
    await push_audit_event(
        redis,
        event_type="helpdesk.ticket_deleted",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="helpdesk_ticket",
        resource_id=str(ticket.id),
        metadata={
            "number": number,
            "subject": ticket.subject,
            "previous_status": ticket.status,
        },
    )


# ===========================================================================
# Attachments (Этап 4)
# ===========================================================================


async def _file_chunk_iter(path: Path) -> AsyncIterator[bytes]:
    """Async generator: читает локальный файл чанками для StreamingResponse
    через ``aiofiles`` (НЕ FileResponse, НЕ X-Accel-Redirect — ТЗ §1.3.4)."""
    import aiofiles

    async with aiofiles.open(path, "rb") as f:
        while True:
            chunk = await f.read(1024 * 1024)
            if not chunk:
                break
            yield chunk


async def _can_read_archived_ticket(
    db: DbDep, *, user: CurrentUser, ticket: archive_service.ArchivedTicket
) -> bool:
    """Archive ACL mirrors live downloads without reviving mutable rows."""
    if ticket.row.requester_user_id == user.id or user.role == "admin":
        return True
    return (
        await db.execute(select(HelpdeskAgent.user_id).where(HelpdeskAgent.user_id == user.id))
    ).first() is not None


@router.get(
    "/tickets/{ticket_id}/archive-attachments/{filename}",
    summary="Скачать вложение из бессрочного архива helpdesk",
    response_class=StreamingResponse,
)
async def download_archived_attachment(
    ticket_id: uuid.UUID,
    filename: str,
    user: CurrentUser,
    db: DbDep,
) -> StreamingResponse:
    ticket = await archive_service.fetch_archived_ticket(db, ticket_id=ticket_id)
    if ticket is None or not await _can_read_archived_ticket(db, user=user, ticket=ticket):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    # Reuse the same strict filename guard as the live storage layer. Archive
    # metadata is the allow-list, so a guessed disk filename cannot be served.
    if not attachments_service._SAFE_FILENAME_RE.match(filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    payload = ticket.row.payload if isinstance(ticket.row.payload, dict) else {}
    raw_meta = payload.get("attachments_meta", [])
    meta = (
        next(
            (
                item
                for item in raw_meta
                if isinstance(item, dict) and item.get("filename") == filename
            ),
            None,
        )
        if isinstance(raw_meta, list)
        else None
    )
    if meta is None:
        # New snapshots nest attachment metadata by message; accept that shape
        # too without weakening the archive allow-list.
        meta = next(
            (
                item
                for message in ticket.messages
                for item in (
                    message.get("attachments", [])
                    if isinstance(message.get("attachments"), list)
                    else []
                )
                if isinstance(item, dict) and item.get("filename") == filename
            ),
            None,
        )
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    path = attachments_service.ticket_dir(ticket.row.number) / filename
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    raw_original_name = meta.get("original_name")
    original_name = raw_original_name if isinstance(raw_original_name, str) else filename
    content_type = (
        meta.get("content_type")
        if isinstance(meta.get("content_type"), str)
        else "application/octet-stream"
    )
    return StreamingResponse(
        _file_chunk_iter(path),
        media_type=content_type,
        headers={
            "Content-Disposition": _rfc5987_filename(original_name),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/attachments/{attachment_id}",
    summary="Скачать вложение (StreamingResponse из локального файла)",
    response_class=StreamingResponse,
)
async def download_attachment(
    attachment_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> StreamingResponse:
    att, ticket = await attachments_service.fetch_for_download(
        db, attachment_id=attachment_id, user=user
    )
    path = attachments_service.disk_path(att, ticket.number)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return StreamingResponse(
        _file_chunk_iter(path),
        media_type=att.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": _rfc5987_filename(att.original_name),
            "X-Content-Type-Options": "nosniff",
        },
    )
