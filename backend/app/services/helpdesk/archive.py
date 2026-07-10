"""Archive service for helpdesk (ТЗ §3.7, §8).

Перенос закрытых тикетов (``closed_at < NOW() - HELPDESK_ARCHIVE_AFTER_DAYS``)
в партиционированную таблицу ``helpdesk_tickets_archive`` (jsonb-снимок) с
удалением строки из ``helpdesk_tickets`` (сообщения/вложения уходят по
CASCADE). Файлы вложений физически остаются на диске ещё
``HELPDESK_ARCHIVE_FILES_TTL_DAYS``, после чего вся папка тикета удаляется
cron'ом ``cleanup_helpdesk_attachments``.

Партиции архива создаются помесячно (аналог ``audit_partitions``) — см.
``ensure_helpdesk_archive_partitions`` + cron
``create_next_helpdesk_archive_partition`` в ``worker/tasks/helpdesk.py``.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    HELPDESK_ARCHIVE_AFTER_DAYS,
    HELPDESK_ARCHIVE_FILES_TTL_DAYS,
)
from app.core.logging import get_logger
from app.models.helpdesk import (
    HelpdeskAttachment,
    HelpdeskMessage,
    HelpdeskTicket,
    HelpdeskTicketArchive,
)
from app.services.helpdesk.attachments import delete_ticket_dir

logger = get_logger(__name__)

ARCHIVE_TABLE = "helpdesk_tickets_archive"


async def archive_closed_tickets(db: AsyncSession) -> int:
    """Перенести тикеты со статусом ``closed`` и ``closed_at`` старше
    ``HELPDESK_ARCHIVE_AFTER_DAYS`` в архив; вернуть кол-во архивированных."""
    cutoff = datetime.now(UTC) - timedelta(days=HELPDESK_ARCHIVE_AFTER_DAYS)
    res = await db.execute(
        select(HelpdeskTicket)
        .where(HelpdeskTicket.status == "closed", HelpdeskTicket.closed_at < cutoff)
        .order_by(HelpdeskTicket.closed_at)
    )
    tickets = res.scalars().unique().all()
    archived = 0
    for ticket in tickets:
        await _archive_one(db, ticket)
        archived += 1
    # Фиксируем перенос атомарно: _archive_one делает только flush (добавляет
    # архивную строку + удаляет живую), без commit изменения откатываются на
    # выходе из сессии воркера (AsyncSessionLocal autocommit=False). Раньше
    # commit отсутствовал → архивация была silent no-op в проде.
    if archived:
        await db.commit()
        logger.info("helpdesk.archive.done", archived=archived)
    return archived


async def _archive_one(db: AsyncSession, ticket: HelpdeskTicket) -> None:
    # Грузим сообщения и метаданные вложений.
    msgs_res = await db.execute(
        select(HelpdeskMessage).where(HelpdeskMessage.ticket_id == ticket.id)
    )
    messages = msgs_res.scalars().all()
    atts_res = await db.execute(
        select(HelpdeskAttachment).where(HelpdeskAttachment.ticket_id == ticket.id)
    )
    attachments = atts_res.scalars().all()

    payload = {
        "ticket": {
            "id": str(ticket.id),
            "number": ticket.number,
            "subject": ticket.subject,
            "description": ticket.description,
            "status": ticket.status,
            "source": ticket.source,
            "requester_email": ticket.requester_email,
            "requester_name": ticket.requester_name,
            "created_at": ticket.created_at.isoformat(),
        },
        "messages": [
            {
                "id": str(m.id),
                "direction": m.direction,
                "visibility": m.visibility,
                "body_text": m.body_text,
                "author_email": m.author_email,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "attachments_meta": [
            {
                "filename": a.filename,
                "original_name": a.original_name,
                "content_type": a.content_type,
                "size_bytes": a.size_bytes,
            }
            for a in attachments
        ],
    }

    archive_row = HelpdeskTicketArchive(
        id=ticket.id,
        number=ticket.number,
        subject=ticket.subject,
        requester_email=ticket.requester_email,
        requester_user_id=ticket.requester_user_id,
        assignee_user_id=ticket.assignee_user_id,
        opened_at=ticket.created_at,
        closed_at=ticket.closed_at,
        closed_by_user_id=ticket.closed_by_user_id,
        payload=json.loads(json.dumps(payload, default=str)),
    )
    db.add(archive_row)
    # Удаление живой строки → сообщения/вложения уйдут по CASCADE.
    await db.delete(ticket)
    await db.flush()


async def cleanup_archived_files(db: AsyncSession) -> int:
    """Удалить папки тикетов на диске, чьи архивированные записи старше
    ``HELPDESK_ARCHIVE_FILES_TTL_DAYS``. Best-effort: неверные имена/ошибки FS
    пропускаются. Возвращает кол-во удалённых папок."""
    cutoff = datetime.now(UTC) - timedelta(days=HELPDESK_ARCHIVE_FILES_TTL_DAYS)
    res = await db.execute(
        select(HelpdeskTicketArchive.number, HelpdeskTicketArchive.archived_at).where(
            HelpdeskTicketArchive.archived_at < cutoff
        )
    )
    removed = 0
    for number, _archived_at in res.all():
        delete_ticket_dir(number)
        removed += 1
    if removed:
        logger.info("helpdesk.cleanup_archived_files.done", removed=removed)
    return removed


async def fetch_archive_list(
    db: AsyncSession,
    *,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[HelpdeskTicketArchive], int]:
    """Список архивных тикетов (read-only, admin-only на уровне роутера).
    Простой ILIKE-поиск по subject/requester_email (FTS не нужен в MVP)."""
    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(
            (HelpdeskTicketArchive.subject.ilike(like))
            | (HelpdeskTicketArchive.requester_email.ilike(like))
        )
    total_res = await db.execute(
        select(func.count()).select_from(HelpdeskTicketArchive).where(*conditions)
    )
    total = int(total_res.scalar_one())
    res = await db.execute(
        select(HelpdeskTicketArchive)
        .where(*conditions)
        .order_by(HelpdeskTicketArchive.closed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(res.scalars().all()), total


async def fetch_archive_item(
    db: AsyncSession, *, archive_id: uuid.UUID
) -> HelpdeskTicketArchive | None:
    res = await db.execute(
        select(HelpdeskTicketArchive).where(HelpdeskTicketArchive.id == archive_id).limit(1)
    )
    return res.scalars().first()


# re-export для cron-cleanup (использует raw SQL delete партиций при необходимости)
__all__ = [
    "ARCHIVE_TABLE",
    "archive_closed_tickets",
    "cleanup_archived_files",
    "fetch_archive_item",
    "fetch_archive_list",
]
