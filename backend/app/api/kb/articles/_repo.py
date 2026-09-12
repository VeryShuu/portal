"""Pure data-access helpers for KB article endpoints.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
The dynamic list query is *built* in the route (filters/visibility) and only
its execution is delegated here, so request-shaping logic stays with the
endpoint while raw ``db.execute`` calls live in this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Integer, Select, case, cast, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Executable

from app.models.kb import KbArticle, KbArticleFeedback, KbSection, KbTag
from app.services.kb_tree import KB_SECTIONS_DESCENDANTS_SQL


async def get_active_section(db: AsyncSession, section_id: uuid.UUID) -> KbSection | None:
    res = await db.execute(
        select(KbSection).where(
            KbSection.id == section_id,
            KbSection.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


async def get_article_for_update(db: AsyncSession, article_id: uuid.UUID) -> KbArticle | None:
    res = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
        .with_for_update()
    )
    return res.scalar_one_or_none()


async def get_article_with_tags(db: AsyncSession, article_id: uuid.UUID) -> KbArticle | None:
    res = await db.execute(
        select(KbArticle).options(selectinload(KbArticle.tags)).where(KbArticle.id == article_id)
    )
    return res.scalar_one_or_none()


async def apply_article_update(
    db: AsyncSession,
    *,
    article_id: uuid.UUID,
    expected_version: int,
    values: dict[str, Any],
) -> bool:
    res = await db.execute(
        update(KbArticle)
        .where(KbArticle.id == article_id, KbArticle.version == expected_version)
        .values(**values)
        .returning(KbArticle.id)
    )
    return res.fetchone() is not None


async def get_feedback_summary(
    db: AsyncSession, *, article_id: uuid.UUID, user_id: uuid.UUID
) -> Any:
    res = await db.execute(
        select(
            func.count(1).filter(KbArticleFeedback.is_helpful.is_(True)).label("helpful"),
            func.count(1).filter(KbArticleFeedback.is_helpful.is_(False)).label("not_helpful"),
            func.max(
                case(
                    (
                        KbArticleFeedback.user_id == user_id,
                        cast(KbArticleFeedback.is_helpful, Integer),
                    ),
                    else_=None,
                )
            ).label("user_fb"),
        ).where(KbArticleFeedback.article_id == article_id)
    )
    return res.one()


async def get_descendant_section_ids(db: AsyncSession, section_id: uuid.UUID) -> list[Any]:
    res = await db.execute(
        text(KB_SECTIONS_DESCENDANTS_SQL),
        {"section_id": str(section_id)},
    )
    return [row[0] for row in res.fetchall()]


async def get_tag_by_slug(db: AsyncSession, slug: str) -> KbTag | None:
    res = await db.execute(select(KbTag).where(KbTag.slug == slug))
    return res.scalar_one_or_none()


async def count_articles(db: AsyncSession, stmt: Select[Any]) -> int:
    count_stmt = select(func.count()).select_from(stmt.subquery())
    res = await db.execute(count_stmt)
    return res.scalar_one()


async def fetch_articles(db: AsyncSession, stmt: Executable) -> Sequence[KbArticle]:
    res = await db.execute(stmt)
    return res.scalars().all()
