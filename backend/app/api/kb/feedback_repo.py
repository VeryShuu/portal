"""Pure data-access helpers for KB article feedback.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticleFeedback


async def get_user_feedback(
    db: AsyncSession, *, article_id: uuid.UUID, user_id: uuid.UUID
) -> KbArticleFeedback | None:
    res = await db.execute(
        select(KbArticleFeedback).where(
            KbArticleFeedback.article_id == article_id,
            KbArticleFeedback.user_id == user_id,
        )
    )
    return res.scalar_one_or_none()


async def count_feedback(db: AsyncSession, article_id: uuid.UUID, *, is_helpful: bool) -> int:
    res = await db.execute(
        select(func.count()).where(
            KbArticleFeedback.article_id == article_id,
            KbArticleFeedback.is_helpful.is_(is_helpful),
        )
    )
    return res.scalar_one()
