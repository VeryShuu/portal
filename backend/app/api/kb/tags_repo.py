"""Pure data-access helpers for KB tags.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticle, KbArticleTag, KbTag


async def list_active_tags(db: AsyncSession) -> Sequence[KbTag]:
    res = await db.execute(
        select(KbTag)
        .where(
            KbTag.id.in_(
                select(KbArticleTag.tag_id)
                .join(KbArticle, KbArticle.id == KbArticleTag.article_id)
                .where(KbArticle.deleted_at.is_(None))
                .distinct()
            )
        )
        .order_by(KbTag.name)
    )
    return list(res.scalars())
