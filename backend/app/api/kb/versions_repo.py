"""Pure data-access helpers for KB article versions.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models.kb import KbArticleVersion
from app.models.user import User


async def count_versions(db: AsyncSession, article_id: uuid.UUID) -> int:
    res = await db.execute(select(func.count()).where(KbArticleVersion.article_id == article_id))
    return res.scalar_one()


async def list_versions(
    db: AsyncSession, article_id: uuid.UUID, *, limit: int, offset: int
) -> Sequence[KbArticleVersion]:
    res = await db.execute(
        select(KbArticleVersion)
        .options(defer(KbArticleVersion.body))
        .where(KbArticleVersion.article_id == article_id)
        .order_by(KbArticleVersion.version.desc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().all()


async def get_version_changers(
    db: AsyncSession, changer_ids: set[uuid.UUID]
) -> dict[uuid.UUID, User]:
    if not changer_ids:
        return {}
    res = await db.execute(select(User).where(User.id.in_(changer_ids)))
    return {u.id: u for u in res.scalars()}


async def get_version(
    db: AsyncSession, *, article_id: uuid.UUID, version_number: int
) -> KbArticleVersion | None:
    res = await db.execute(
        select(KbArticleVersion).where(
            KbArticleVersion.article_id == article_id,
            KbArticleVersion.version == version_number,
        )
    )
    return res.scalar_one_or_none()


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()
