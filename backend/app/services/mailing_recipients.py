"""Business logic for the news mailing recipients directory.

HTTP-agnostic CRUD over :class:`MailingRecipient` plus a resolver used by the
news "share by email" flow to turn a list of recipient ids into concrete
addresses. Uniqueness is enforced case-insensitively among non-deleted rows
(matching ``idx_mailing_recipients_email_ci_active``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mailing_recipient import MailingRecipient
from app.schemas.mailing_recipient import (
    CreateMailingRecipientRequest,
    UpdateMailingRecipientRequest,
)


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_recipients(
    db: AsyncSession,
    *,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[MailingRecipient], int]:
    conditions: list[Any] = [MailingRecipient.deleted_at.is_(None)]
    if q:
        like = f"%{_escape_like(q)}%"
        conditions.append(
            MailingRecipient.name.ilike(like, escape="\\")
            | MailingRecipient.email.ilike(like, escape="\\")
        )

    total: int = (
        await db.execute(select(func.count()).select_from(MailingRecipient).where(*conditions))
    ).scalar_one()

    stmt = (
        select(MailingRecipient)
        .where(*conditions)
        .order_by(MailingRecipient.name, MailingRecipient.email)
        .offset(offset)
        .limit(limit)
    )
    items = list((await db.execute(stmt)).scalars().all())
    return items, total


async def get_recipient_or_404(db: AsyncSession, recipient_id: uuid.UUID) -> MailingRecipient:
    result = await db.execute(
        select(MailingRecipient).where(
            MailingRecipient.id == recipient_id,
            MailingRecipient.deleted_at.is_(None),
        )
    )
    recipient = result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    return recipient


async def create_recipient(
    db: AsyncSession,
    body: CreateMailingRecipientRequest,
    created_by: uuid.UUID,
) -> MailingRecipient:
    recipient = MailingRecipient(
        name=body.name,
        email=body.email,
        label=body.label,
        created_by_user_id=created_by,
    )
    db.add(recipient)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recipient with this email already exists",
        ) from exc
    await db.refresh(recipient)
    return recipient


async def update_recipient(
    db: AsyncSession,
    recipient: MailingRecipient,
    body: UpdateMailingRecipientRequest,
) -> list[str]:
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(recipient, field, value)
    recipient.updated_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recipient with this email already exists",
        ) from exc
    await db.refresh(recipient)
    return sorted(changes.keys())


async def soft_delete_recipient(db: AsyncSession, recipient: MailingRecipient) -> None:
    recipient.deleted_at = datetime.now(UTC)
    await db.commit()


async def resolve_recipients(
    db: AsyncSession, recipient_ids: list[uuid.UUID]
) -> list[MailingRecipient]:
    """Resolve recipient ids to active recipients for sending.

    Every id must reference an active (non-deleted) recipient; otherwise a 404
    is raised and nothing is sent. Duplicate ids are de-duplicated while
    preserving the request order.
    """
    unique_ids: list[uuid.UUID] = list(dict.fromkeys(recipient_ids))
    result = await db.execute(
        select(MailingRecipient).where(
            MailingRecipient.id.in_(unique_ids),
            MailingRecipient.deleted_at.is_(None),
        )
    )
    by_id = {r.id: r for r in result.scalars().all()}
    missing = [str(rid) for rid in unique_ids if rid not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown recipient(s): {', '.join(missing)}",
        )
    return [by_id[rid] for rid in unique_ids]
