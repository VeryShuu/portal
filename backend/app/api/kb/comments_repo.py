"""Pure data-access helpers for KB article comments.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticleComment
from app.models.user import User


async def count_comments(db: AsyncSession, article_id: uuid.UUID) -> int:
    res = await db.execute(
        select(func.count()).where(KbArticleComment.article_id == article_id)
    )
    return res.scalar_one()


async def list_comments(
    db: AsyncSession, article_id: uuid.UUID, *, limit: int, offset: int
) -> Sequence[KbArticleComment]:
    res = await db.execute(
        select(KbArticleComment)
        .where(KbArticleComment.article_id == article_id)
        .order_by(KbArticleComment.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().all()


async def get_comment_authors(
    db: AsyncSession, author_ids: set[uuid.UUID]
) -> dict[uuid.UUID, User]:
    if not author_ids:
        return {}
    res = await db.execute(select(User).where(User.id.in_(author_ids)))
    return {u.id: u for u in res.scalars()}


async def get_comment(
    db: AsyncSession, *, article_id: uuid.UUID, comment_id: uuid.UUID
) -> KbArticleComment | None:
    res = await db.execute(
        select(KbArticleComment).where(
            KbArticleComment.id == comment_id,
            KbArticleComment.article_id == article_id,
        )
    )
    return res.scalar_one_or_none()
