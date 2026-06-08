"""Pure data-access helpers for KB sections.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
Each helper performs exactly one ``db.execute`` so the calling route preserves
its original query ordering.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticle, KbSection

_DESCENDANT_CYCLE_SQL = """
                    WITH RECURSIVE descendants AS (
                        SELECT id FROM kb_sections WHERE id = :section_id AND deleted_at IS NULL
                        UNION ALL
                        SELECT s.id FROM kb_sections s
                        JOIN descendants d ON s.parent_id = d.id
                        WHERE s.deleted_at IS NULL
                    )
                    SELECT 1 FROM descendants WHERE id = :parent_id LIMIT 1
                """


async def list_active_sections(db: AsyncSession) -> Sequence[KbSection]:
    res = await db.execute(
        select(KbSection)
        .where(KbSection.deleted_at.is_(None))
        .order_by(KbSection.sort_order, KbSection.title)
    )
    return res.scalars().all()


async def get_active_section(db: AsyncSession, section_id: uuid.UUID) -> KbSection | None:
    res = await db.execute(
        select(KbSection).where(KbSection.id == section_id, KbSection.deleted_at.is_(None))
    )
    return res.scalar_one_or_none()


async def find_section_by_slug(
    db: AsyncSession, *, slug: str, parent_id: uuid.UUID | None
) -> KbSection | None:
    res = await db.execute(
        select(KbSection).where(
            KbSection.slug == slug,
            KbSection.parent_id == parent_id,
        )
    )
    return res.scalar_one_or_none()


async def is_descendant(db: AsyncSession, *, section_id: uuid.UUID, parent_id: uuid.UUID) -> bool:
    res = await db.execute(
        text(_DESCENDANT_CYCLE_SQL),
        {"section_id": str(section_id), "parent_id": str(parent_id)},
    )
    return res.fetchone() is not None


async def has_active_children(db: AsyncSession, section_id: uuid.UUID) -> bool:
    res = await db.execute(
        select(KbSection)
        .where(KbSection.parent_id == section_id, KbSection.deleted_at.is_(None))
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def has_active_articles(db: AsyncSession, section_id: uuid.UUID) -> bool:
    res = await db.execute(
        select(KbArticle)
        .where(KbArticle.section_id == section_id, KbArticle.deleted_at.is_(None))
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def detach_trashed_articles(db: AsyncSession, section_id: uuid.UUID) -> None:
    await db.execute(
        update(KbArticle)
        .where(KbArticle.section_id == section_id, KbArticle.deleted_at.isnot(None))
        .values(section_id=None)
    )
