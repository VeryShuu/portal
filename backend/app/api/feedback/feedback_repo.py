"""Data access layer for the feedback API package."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.feedback import Feedback, FeedbackReply


def _admin_full_load_options() -> tuple[Any, ...]:
    return (
        selectinload(Feedback.replies).joinedload(FeedbackReply.admin),
        selectinload(Feedback.attachments),
    )


async def count_my_feedback(
    db: AsyncSession, *, user_id: uuid.UUID, status_filter: str | None
) -> int:
    conditions = [Feedback.user_id == user_id]
    if status_filter:
        conditions.append(Feedback.status == status_filter)
    res = await db.execute(select(func.count()).select_from(Feedback).where(*conditions))
    return int(res.scalar_one())


async def list_my_feedback(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    status_filter: str | None,
    limit: int,
    offset: int,
) -> Sequence[Feedback]:
    conditions = [Feedback.user_id == user_id]
    if status_filter:
        conditions.append(Feedback.status == status_filter)
    res = await db.execute(
        select(Feedback)
        .where(*conditions)
        .options(*_admin_full_load_options())
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().unique().all()


async def fetch_my_feedback(
    db: AsyncSession, *, feedback_id: uuid.UUID, user_id: uuid.UUID
) -> Feedback | None:
    res = await db.execute(
        select(Feedback)
        .where(Feedback.id == feedback_id, Feedback.user_id == user_id)
        .options(*_admin_full_load_options())
    )
    return res.unique().scalar_one_or_none()


async def count_admin_feedback(
    db: AsyncSession,
    *,
    status_filter: str | None,
    category: str | None,
    q: str | None,
) -> int:
    conditions = []
    if status_filter:
        conditions.append(Feedback.status == status_filter)
    if category:
        conditions.append(Feedback.category == category)
    if q:
        conditions.append(Feedback.message.ilike(f"%{q}%"))
    total_q = select(func.count()).select_from(Feedback)
    if conditions:
        total_q = total_q.where(*conditions)
    res = await db.execute(total_q)
    return int(res.scalar_one())


async def list_admin_feedback(
    db: AsyncSession,
    *,
    status_filter: str | None,
    category: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> Sequence[Feedback]:
    conditions = []
    if status_filter:
        conditions.append(Feedback.status == status_filter)
    if category:
        conditions.append(Feedback.category == category)
    if q:
        conditions.append(Feedback.message.ilike(f"%{q}%"))
    list_q = (
        select(Feedback)
        .options(*_admin_full_load_options())
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        list_q = list_q.where(*conditions)
    res = await db.execute(list_q)
    return res.scalars().unique().all()


async def fetch_admin_feedback(db: AsyncSession, feedback_id: uuid.UUID) -> Feedback | None:
    res = await db.execute(
        select(Feedback).where(Feedback.id == feedback_id).options(*_admin_full_load_options())
    )
    return res.unique().scalar_one_or_none()


async def fetch_feedback_simple(db: AsyncSession, feedback_id: uuid.UUID) -> Feedback | None:
    res = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    return res.scalar_one_or_none()


async def fetch_feedback_with_attachments(
    db: AsyncSession, feedback_id: uuid.UUID
) -> Feedback | None:
    res = await db.execute(
        select(Feedback)
        .where(Feedback.id == feedback_id)
        .options(selectinload(Feedback.attachments))
    )
    return res.unique().scalar_one_or_none()
