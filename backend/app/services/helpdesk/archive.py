"""Archive service for helpdesk (ТЗ §3.7, §8).

Перенос закрытых тикетов (``closed_at < NOW() - HELPDESK_ARCHIVE_AFTER_DAYS``)
в партиционированную таблицу ``helpdesk_tickets_archive`` (jsonb-снимок) с
удалением строки из ``helpdesk_tickets`` (сообщения/вложения уходят по
CASCADE). Файлы остаются в ``/data/helpdesk`` бессрочно: архив helpdesk —
значимый бизнес-документ, а не кэш.

Партиции архива создаются помесячно (аналог ``audit_partitions``) — см.
``ensure_helpdesk_archive_partitions`` + cron
``create_next_helpdesk_archive_partition`` в ``worker/tasks/helpdesk.py``.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import (
    HELPDESK_ARCHIVE_AFTER_DAYS,
    HELPDESK_ARCHIVE_BATCH_SIZE,
)
from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket, HelpdeskTicketArchive
from app.models.user import User
from app.schemas.helpdesk import HelpdeskStatus

logger = get_logger(__name__)


@dataclass(frozen=True)
class ArchivedTicket:
    """Read-model archived ticket.

    The archive intentionally stores an immutable JSON snapshot, so it cannot
    be represented as ``HelpdeskTicket``. Keeping a dedicated read model makes
    that boundary explicit and prevents archive details from accidentally being
    used by mutation services.
    """

    row: HelpdeskTicketArchive
    description: str
    description_html: str | None
    source: str
    requester_name: str | None
    messages: list[dict[str, Any]]

    @property
    def id(self) -> uuid.UUID:
        return self.row.id


def _payload_ticket(row: HelpdeskTicketArchive) -> dict[str, Any]:
    ticket = row.payload.get("ticket") if isinstance(row.payload, dict) else None
    return ticket if isinstance(ticket, dict) else {}


def _as_archived_ticket(row: HelpdeskTicketArchive) -> ArchivedTicket:
    payload_ticket = _payload_ticket(row)
    raw_messages = row.payload.get("messages", []) if isinstance(row.payload, dict) else []
    messages = (
        [m for m in raw_messages if isinstance(m, dict)] if isinstance(raw_messages, list) else []
    )
    source = payload_ticket.get("source")
    return ArchivedTicket(
        row=row,
        description=str(payload_ticket.get("description") or ""),
        description_html=payload_ticket.get("description_html")
        if isinstance(payload_ticket.get("description_html"), str)
        else None,
        source=source if source in {"web", "email"} else "email",
        requester_name=payload_ticket.get("requester_name")
        if isinstance(payload_ticket.get("requester_name"), str)
        else None,
        messages=messages,
    )


async def list_archived_tickets(
    db: AsyncSession,
    *,
    requester_user_id: uuid.UUID | None = None,
    assignee_user_id: uuid.UUID | None = None,
    assigned: bool = False,
    unassigned: bool = False,
    source: str | None = None,
    query: str | None = None,
) -> list[ArchivedTicket]:
    """Return archive records for the closed-ticket views.

    JSONB fields are deliberately filtered in Python here: archive partitions
    are cold storage and this keeps legacy snapshots (whose shape predates the
    read API) compatible. The caller merges these with live ``closed`` rows and
    paginates only after the merge, so no archived ticket silently disappears.
    """
    conditions = []
    if requester_user_id is not None:
        conditions.append(HelpdeskTicketArchive.requester_user_id == requester_user_id)
    if assignee_user_id is not None:
        conditions.append(HelpdeskTicketArchive.assignee_user_id == assignee_user_id)
    elif assigned:
        conditions.append(HelpdeskTicketArchive.assignee_user_id.is_not(None))
    elif unassigned:
        conditions.append(HelpdeskTicketArchive.assignee_user_id.is_(None))
    rows = (
        (
            await db.execute(
                select(HelpdeskTicketArchive)
                .where(*conditions)
                .order_by(HelpdeskTicketArchive.closed_at.desc())
            )
        )
        .scalars()
        .all()
    )
    result = [_as_archived_ticket(row) for row in rows]
    needle = query.strip().lower() if query else ""
    if source:
        result = [item for item in result if item.source == source]
    if needle:
        result = [
            item
            for item in result
            if needle in item.row.subject.lower()
            or needle in item.row.requester_email.lower()
            or needle in item.description.lower()
            or any(
                needle in str(message.get("body_text") or "").lower() for message in item.messages
            )
        ]
    return result


async def fetch_archived_ticket(db: AsyncSession, *, ticket_id: uuid.UUID) -> ArchivedTicket | None:
    row = (
        (
            await db.execute(
                select(HelpdeskTicketArchive).where(HelpdeskTicketArchive.id == ticket_id)
            )
        )
        .scalars()
        .one_or_none()
    )
    return _as_archived_ticket(row) if row is not None else None


async def resolve_archived_requester_user(
    db: AsyncSession, *, ticket: ArchivedTicket
) -> User | None:
    if ticket.row.requester_user_id is not None:
        return (
            (await db.execute(select(User).where(User.id == ticket.row.requester_user_id)))
            .scalars()
            .one_or_none()
        )
    return None


async def archive_closed_tickets(
    db: AsyncSession, *, batch_size: int = HELPDESK_ARCHIVE_BATCH_SIZE
) -> int:
    """Move eligible closed tickets in bounded, atomic batches.

    Each batch eagerly loads messages and their attachments, commits separately
    and therefore never holds the whole archive backlog in one transaction.
    Archive files are deliberately retained indefinitely.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    cutoff = datetime.now(UTC) - timedelta(days=HELPDESK_ARCHIVE_AFTER_DAYS)
    backlog_before = await db.scalar(
        select(func.count())
        .select_from(HelpdeskTicket)
        .where(HelpdeskTicket.status == HelpdeskStatus.closed, HelpdeskTicket.closed_at < cutoff)
    )
    archived = 0
    batches = 0
    started = time.monotonic()
    while True:
        res = await db.execute(
            select(HelpdeskTicket)
            .where(
                HelpdeskTicket.status == HelpdeskStatus.closed,
                HelpdeskTicket.closed_at < cutoff,
            )
            .order_by(HelpdeskTicket.closed_at)
            .limit(batch_size)
            .with_for_update()
            .options(
                selectinload(HelpdeskTicket.messages).selectinload(HelpdeskMessage.attachments)
            )
        )
        tickets = res.scalars().unique().all()
        if not tickets:
            break
        for ticket in tickets:
            await _archive_one(db, ticket)
        await db.commit()
        archived += len(tickets)
        batches += 1
        logger.info("helpdesk.archive.batch_done", size=len(tickets), total=archived)
    logger.info(
        "helpdesk.archive.done",
        backlog_before=backlog_before or 0,
        archived=archived,
        batches=batches,
        duration_seconds=round(time.monotonic() - started, 3),
    )
    return archived


async def _archive_one(db: AsyncSession, ticket: HelpdeskTicket) -> None:
    # Loaded by the batch query; no per-ticket query fan-out.
    messages = list(ticket.messages)
    attachments = [attachment for message in messages for attachment in message.attachments]
    last_activity_at = (
        getattr(ticket, "last_activity_at", None) or ticket.closed_at or ticket.created_at
    )

    payload = {
        "ticket": {
            "id": str(ticket.id),
            "number": ticket.number,
            "subject": ticket.subject,
            "description": ticket.description,
            # ``description_html`` (rich-редактор TipTap) сохраняется в архив,
            # иначе форматирование заявки терялось при закрытии (only plain
            # ``description`` было раньше). ``None`` сериализуется как null —
            # legacy-заявки без html остаются читаемыми.
            "description_html": ticket.description_html,
            "status": ticket.status,
            "source": ticket.source,
            "requester_email": ticket.requester_email,
            "requester_name": ticket.requester_name,
            "created_at": ticket.created_at.isoformat(),
            "last_activity_at": last_activity_at.isoformat(),
        },
        "messages": [
            {
                "id": str(m.id),
                "direction": m.direction,
                "body_text": m.body_text,
                # ``body_html`` (rich-редактор ответов) — для полноты архива.
                # Без него форматированные ответы агентов теряли разметку.
                "body_html": m.body_html,
                "author_email": m.author_email,
                "author_name": getattr(m, "author_name", None),
                "author_user_id": str(m.author_user_id)
                if getattr(m, "author_user_id", None)
                else None,
                "source": getattr(m, "source", ticket.source),
                "cc": getattr(m, "cc", None) or [],
                "created_at": m.created_at.isoformat(),
                "attachments": [
                    {
                        "id": str(a.id),
                        "filename": a.filename,
                        "original_name": a.original_name,
                        "content_type": a.content_type,
                        "size_bytes": a.size_bytes,
                        "created_at": getattr(a, "created_at", m.created_at).isoformat(),
                        "is_inline": getattr(a, "is_inline", False),
                        "content_id": getattr(a, "content_id", None),
                    }
                    for a in attachments
                    if a.message_id == m.id
                ],
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
    """Compatibility no-op for the retired archive-file cleanup cron.

    Worker scheduling is retained to make deployment rollback harmless, but an
    archived ticket's files must remain recoverable for its entire lifetime.
    """
    del db
    logger.debug("helpdesk.cleanup_archived_files.skipped", reason="indefinite_retention")
    return 0


# ``ARCHIVE_TABLE`` живёт в ``archive_partitions.py`` (используется при
# ``CREATE TABLE ... PARTITION OF``); здесь не дублируем — импорта ниоткуда нет.
__all__ = [
    "archive_closed_tickets",
    "cleanup_archived_files",
]
