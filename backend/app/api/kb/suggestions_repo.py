"""Pure data-access helpers for KB suggestions (edit proposals).

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticle, KbSuggestion
from app.models.user import User


async def list_suggestions(db: AsyncSession, article_id: uuid.UUID) -> Sequence[KbSuggestion]:
    res = await db.execute(
        select(KbSuggestion)
        .where(KbSuggestion.article_id == article_id)
        .order_by(KbSuggestion.created_at.desc())
    )
    return res.scalars().all()


async def get_suggestion_authors(
    db: AsyncSession, author_ids: set[uuid.UUID]
) -> dict[uuid.UUID, User]:
    if not author_ids:
        return {}
    res = await db.execute(select(User).where(User.id.in_(author_ids)))
    return {u.id: u for u in res.scalars()}


async def get_suggestion(db: AsyncSession, suggestion_id: uuid.UUID) -> KbSuggestion | None:
    res = await db.execute(select(KbSuggestion).where(KbSuggestion.id == suggestion_id))
    return res.scalar_one_or_none()


async def get_article(db: AsyncSession, article_id: uuid.UUID) -> KbArticle | None:
    res = await db.execute(select(KbArticle).where(KbArticle.id == article_id))
    return res.scalar_one_or_none()
