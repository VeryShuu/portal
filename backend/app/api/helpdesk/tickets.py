"""Ticket endpoints for the Helpdesk module (Этапы 2–3).

Две зоны прав:
* Инициатор (``CurrentUser``) — ``/tickets/my*`` и ``POST /tickets``.
  ``internal``-сообщения и чужие тикеты отсекаются (ACL «только свои»).
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

from app.api.deps import CurrentUser, DbDep, HelpdeskAgentDep, RedisDep
from app.api.helpdesk._common import (
    build_requester_profile,
    message_to_out,
    ticket_to_agent_out,
    ticket_to_list_out,
    ticket_to_out,
)
from app.api.kb._common import _rfc5987_filename
from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskMailboxSettings, HelpdeskMessage, HelpdeskTicket
from app.models.user import User
from app.schemas.helpdesk import (
    HelpdeskVisibility,
    MessageCreateIn,
    MessageOut,
    RequesterProfileOut,
    TicketAgentOut,
    TicketAssignIn,
    TicketCreateIn,
    TicketListOut,
    TicketOut,
    TicketStatusIn,
)
from app.services.audit import push_audit_event
from app.services.helpdesk import attachments as attachments_service
from app.services.helpdesk import messages as messages_service
from app.services.helpdesk import notifications as notifications_service
from app.services.helpdesk import tickets as tickets_service
from app.services.helpdesk.email_quote import (
    build_reply_marker_html,
    build_reply_marker_plain,
)
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


async def _try_send(coro: Awaitable[object], *, context: str) -> None:
    """Best-effort отправка email через outbox: сбой enqueue (БД, payload) не
    должен ломать бизнес-операцию (назначение уже зафиксировано в БД)."""
    try:
        await coro
    except Exception as exc:
        logger.warning("helpdesk.email_enqueue_failed", context=context, error=str(exc))


# Допустимые значения ?status для list-эндпоинтов (ТЗ §3.1).
_TICKET_STATUSES = frozenset({"new", "open", "pending", "resolved", "closed"})
_TICKET_SOURCES = frozenset({"email", "web"})


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
    summary="Создать заявку через веб-форму (multipart/form-data)",
    dependencies=[Depends(RateLimiter(times=5, minutes=1))],
)
async def create_ticket(
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    subject: str = Form(..., min_length=1, max_length=500),
    description: str = Form(..., min_length=1, max_length=20000),
    files: list[UploadFile] = File(default=[]),
) -> TicketOut:
    payload = TicketCreateIn(subject=subject, description=description)
    ticket = await tickets_service.create_ticket(db, user=user, payload=payload, files=files)
    await _try_notify(
        notifications_service.notify_ticket_created(db, redis, ticket=ticket),
        context="ticket_created",
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
    return ticket_to_out(ticket, requester_profile=build_requester_profile(user))


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
    body_text: str = Form(..., min_length=1, max_length=20000),
    files: list[UploadFile] = File(default=[]),
) -> MessageOut:
    ticket = await tickets_service.fetch_ticket_for_user(db, ticket_id=ticket_id, user_id=user.id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    payload = MessageCreateIn(body_text=body_text)
    message = await messages_service.add_requester_reply(
        db, ticket=ticket, user=user, payload=payload, files=files
    )
    await _try_notify(
        notifications_service.notify_requester_reply(
            db, redis, ticket=ticket, body_preview=message.body_text
        ),
        context="requester_reply",
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


async def _load_agent_ticket(db: DbDep, ticket_id: uuid.UUID) -> HelpdeskTicket:
    ticket = await tickets_service.fetch_ticket_for_agent(db, ticket_id=ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ticket


async def _ticket_requester_profile(
    db: DbDep, *, ticket: HelpdeskTicket
) -> RequesterProfileOut | None:
    """Профиль заявителя для карточки агента. Для гостевых email-заявок —
    fallback-поиск сотрудника по email; не найден → ``None`` (блок скрыт)."""
    requester = await tickets_service.resolve_requester_user(db, ticket=ticket)
    return build_requester_profile(requester)


async def _load_user(db: DbDep, user_id: uuid.UUID) -> User | None:
    from sqlalchemy import select

    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalars().one_or_none()


async def _load_mailbox(db: DbDep) -> HelpdeskMailboxSettings | None:
    """Singleton helpdesk_mailbox_settings (id=1) или None, если не настроен."""
    from sqlalchemy import select

    res = await db.execute(
        select(HelpdeskMailboxSettings).where(HelpdeskMailboxSettings.id == 1)
    )
    return res.scalars().one_or_none()


def _support_domain(mailbox: HelpdeskMailboxSettings | None) -> str | None:
    """Домен из ``support_address`` (часть после ``@``). None, если пуст/невалиден."""
    if mailbox is None:
        return None
    addr = (mailbox.support_address or "").strip()
    if "@" not in addr:
        return None
    domain = addr.split("@", 1)[1].strip()
    return domain or None


async def _collect_ticket_references(
    db: DbDep, *, ticket_id: uuid.UUID, exclude_message_id: uuid.UUID | None = None
) -> list[str]:
    """Цепочка ``email_message_id`` предшествующих сообщений тикета (для
    ``In-Reply-To``/``References``). Опционально исключает свежее сообщение."""
    from sqlalchemy import select

    q = select(HelpdeskMessage.email_message_id).where(
        HelpdeskMessage.ticket_id == ticket_id,
        HelpdeskMessage.email_message_id.is_not(None),
    )
    if exclude_message_id is not None:
        q = q.where(HelpdeskMessage.id != exclude_message_id)
    q = q.order_by(HelpdeskMessage.created_at)
    res = await db.execute(q)
    return [r for r in res.scalars().all() if r]


async def _try_enqueue_outbound(
    db: DbDep,
    *,
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    mailbox: HelpdeskMailboxSettings,
) -> None:
    """Собрать payload и поставить исходящее письмо в outbox (best-effort).
    Содержимое файлов НЕ кладётся в payload — только метаданные (§5.2)."""
    from sqlalchemy import select

    from app.models.helpdesk import HelpdeskAttachment
    from app.services.email_outbox import KIND_HELPDESK, enqueue_outbox_email

    references = await _collect_ticket_references(
        db, ticket_id=ticket.id, exclude_message_id=message.id
    )

    atts_res = await db.execute(
        select(HelpdeskAttachment).where(HelpdeskAttachment.message_id == message.id)
    )
    attachments_meta = [
        {
            "filename": a.filename,
            "original_name": a.original_name,
            "content_type": a.content_type,
        }
        for a in atts_res.scalars().all()
    ]

    support_domain = _support_domain(mailbox)
    # Маркер-разделитель для отсечения цитаты при ответе заявителя (email_quote).
    # Добавляется ТОЛЬКО в outbox-копии тела — сохранённое в БД ``HelpdeskMessage``
    # не мутируется (иначе ``db.commit()`` ниже испортит ленту портала).
    # ``message`` уже закоммичен в ``add_agent_message``, здесь только чтение.
    reply_marker_plain = build_reply_marker_plain(ticket.number)
    reply_marker_html = build_reply_marker_html(ticket.number)
    await enqueue_outbox_email(
        db,
        kind=KIND_HELPDESK,
        to_email=ticket.requester_email,
        subject=f"[#TKT-{ticket.number}] {ticket.subject}",
        body_html=(message.body_html or f"<pre>{message.body_text}</pre>")
        + reply_marker_html,
        body_text=message.body_text + reply_marker_plain,
        payload={
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.number,
            "message_id_header": message.email_message_id,
            "in_reply_to": references[-1] if references else None,
            "references": references,
            "reply_to": f"support+TKT-{ticket.number}@{support_domain}",
            "subject_original": ticket.subject,
            "support_domain": support_domain,
            "attachments": attachments_meta,
        },
        related_resource_type="helpdesk_ticket",
        related_resource_id=ticket.id,
        created_by_user_id=message.author_user_id,
    )
    await db.commit()


async def _try_enqueue_assigned_email(
    db: DbDep,
    *,
    ticket: HelpdeskTicket,
    assignee: User,
    actor: User,
    mailbox: HelpdeskMailboxSettings,
) -> None:
    """Email-уведомление инициатору о назначении ответственного (ТЗ §6).

    Best-effort: только при сконфигурированном mailbox (есть ``support_domain``).
    Письмо входит в email-тред тикета — токен ``[#TKT-{number}]`` в теме и
    ``References`` обеспечивают, что ответ заявителя вернётся в тикет даже без
    живого ``In-Reply-To``. ``Message-ID`` генерируется из свежего uuid (это
    системное письмо, не ``helpdesk_messages``), но в формате треда
    (``tkn-{number}-{uuid}@domain``), чтобы ответ попал в ``references``.
    """
    from app.services.email_outbox import KIND_HELPDESK, enqueue_outbox_email
    from app.services.helpdesk.notifications import (
        build_assigned_email_bodies,
        build_assigned_email_subject,
    )

    support_domain = _support_domain(mailbox)
    references = await _collect_ticket_references(db, ticket_id=ticket.id)

    # Генерируем Message-ID в каноническом формате треда тикета. Используется
    # свежий uuid (это уведомление, не HelpdeskMessage), но он валиден как
    # ``References``-ancestor для будущих ответов.
    message_uuid = uuid.uuid4()
    message_id_header = f"<tkn-{ticket.number}-{message_uuid}@{support_domain}>"

    plain, html_body = build_assigned_email_bodies(ticket, assignee)
    await enqueue_outbox_email(
        db,
        kind=KIND_HELPDESK,
        to_email=ticket.requester_email,
        subject=build_assigned_email_subject(ticket),
        body_html=html_body,
        body_text=plain,
        payload={
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.number,
            "message_id_header": message_id_header,
            "in_reply_to": references[-1] if references else None,
            "references": references,
            "reply_to": f"support+TKT-{ticket.number}@{support_domain}",
            "subject_original": ticket.subject,
            "support_domain": support_domain,
            "attachments": [],
        },
        related_resource_type="helpdesk_ticket",
        related_resource_id=ticket.id,
        created_by_user_id=actor.id,
    )
    await db.commit()


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
    q: str | None = Query(default=None, min_length=0, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TicketListOut:
    status_filter = _validate_status_filter(status_filter)
    source = _validate_source(source)
    total = await tickets_service.count_agent_tickets(
        db,
        status_filter=status_filter,
        assignee_id=assignee,
        unassigned=unassigned,
        source=source,
        query=q,
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
    )
    return TicketListOut(
        items=[ticket_to_list_out(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


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
    ticket = await _load_agent_ticket(db, ticket_id)
    profile = await _ticket_requester_profile(db, ticket=ticket)
    return ticket_to_agent_out(ticket, requester_profile=profile)


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ответ агента (public/internal)",
)
async def add_agent_message(
    ticket_id: uuid.UUID,
    agent: HelpdeskAgentDep,
    db: DbDep,
    redis: RedisDep,
    body_text: str = Form(..., min_length=1, max_length=20000),
    body_html: str | None = Form(default=None, max_length=50000),
    visibility: str = Form(default="public"),
    files: list[UploadFile] = File(default=[]),
) -> MessageOut:
    ticket = await _load_agent_ticket(db, ticket_id)
    payload = MessageCreateIn(
        body_text=body_text,
        body_html=body_html,
        visibility=HelpdeskVisibility(visibility),
    )
    # Mailbox settings: нужен support_domain для генерации Message-ID и
    # формирования исходящего письма. Mailbox может быть не настроен — тогда
    # публичный ответ создаётся, но email не отправляется (только in-app).
    mailbox = await _load_mailbox(db)
    support_domain = _support_domain(mailbox)
    message = await messages_service.add_agent_reply(
        db,
        ticket=ticket,
        agent=agent,
        payload=payload,
        files=files,
        support_domain=support_domain,
    )
    if payload.visibility == HelpdeskVisibility.public:
        await _try_notify(
            notifications_service.notify_agent_reply(
                db, redis, ticket=ticket, body_preview=message.body_text
            ),
            context="agent_reply",
        )
        # Outbound email (только если mailbox сконфигурирован). Best-effort.
        if mailbox is not None and support_domain and message.email_message_id:
            await _try_enqueue_outbound(db, ticket=ticket, message=message, mailbox=mailbox)
    await push_audit_event(
        redis,
        event_type="helpdesk.message_added",
        user_id=str(agent.id),
        user_email=agent.email,
        resource_type="helpdesk_ticket",
        resource_id=str(ticket.id),
        metadata={"visibility": message.visibility, "direction": message.direction},
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
    ticket = await _load_agent_ticket(db, ticket_id)
    ticket = await tickets_service.assign_ticket(
        db, ticket=ticket, assignee_id=payload.assignee_user_id
    )
    assignee = await _load_user(db, payload.assignee_user_id)
    if assignee is not None:
        await _try_notify(
            notifications_service.notify_ticket_assigned(
                db, redis, ticket=ticket, assignee=assignee, actor=agent
            ),
            context="ticket_assigned",
        )
        # Email инициатору с ФИО ответственного (ТЗ §6) — только при
        # сконфигурированном mailbox. Best-effort, не ломает назначение.
        mailbox = await _load_mailbox(db)
        if mailbox is not None and _support_domain(mailbox):
            await _try_send(
                _try_enqueue_assigned_email(
                    db, ticket=ticket, assignee=assignee, actor=agent, mailbox=mailbox
                ),
                context="ticket_assigned_email",
            )
    await push_audit_event(
        redis,
        event_type="helpdesk.assigned",
        user_id=str(agent.id),
        user_email=agent.email,
        resource_type="helpdesk_ticket",
        resource_id=str(ticket.id),
        metadata={"assignee_user_id": str(payload.assignee_user_id)},
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
    ticket = await _load_agent_ticket(db, ticket_id)
    if ticket.assignee_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket already assigned",
        )
    ticket = await tickets_service.assign_ticket(db, ticket=ticket, assignee_id=agent.id)
    await _try_notify(
        notifications_service.notify_ticket_assigned(
            db, redis, ticket=ticket, assignee=agent, actor=agent
        ),
        context="ticket_taken",
    )
    # Email инициатору с ФИО ответственного (ТЗ §6) — только при
    # сконфигурированном mailbox. Best-effort.
    mailbox = await _load_mailbox(db)
    if mailbox is not None and _support_domain(mailbox):
        await _try_send(
            _try_enqueue_assigned_email(
                db, ticket=ticket, assignee=agent, actor=agent, mailbox=mailbox
            ),
            context="ticket_taken_email",
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
    try:
        ticket = await tickets_service.change_status(
            db, ticket=ticket, target=payload.status, actor=agent
        )
    except IllegalTransitionError as exc:
        raise _illegal_to_409(exc) from None
    if payload.status in {"resolved", "closed"}:
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
