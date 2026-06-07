"""Pure data-access helpers for notifications.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
Each helper performs exactly one ``db.execute`` so the calling routes preserve
their original query ordering and counts.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def get_stats(db: AsyncSession, user_id: uuid.UUID) -> Any:
    res = await db.execute(
        select(
            func.count().label("total_all"),
            func.count(1).filter(Notification.is_read.is_(False)).label("unread_count"),
        ).where(Notification.user_id == user_id)
    )
    return res.one()


async def list_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    unread_only: bool,
    limit: int,
    offset: int,
) -> Sequence[Notification]:
    query = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        query = query.where(Notification.is_read.is_(False))

    res = await db.execute(query)
    return res.scalars().all()


async def get_notification(
    db: AsyncSession, *, notification_id: uuid.UUID, user_id: uuid.UUID
) -> Notification | None:
    res = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    return res.scalar_one_or_none()


async def mark_all_read(
    db: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=now)
    )
