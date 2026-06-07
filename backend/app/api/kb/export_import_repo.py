"""Pure data-access helpers for KB export/import endpoints.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbSection
from app.models.user import User


async def get_author_name(db: AsyncSession, author_id: uuid.UUID) -> str | None:
    res = await db.execute(select(User.full_name).where(User.id == author_id))
    return res.scalar_one_or_none()


async def get_section(db: AsyncSession, section_id: uuid.UUID) -> KbSection | None:
    res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    return res.scalar_one_or_none()


async def list_root_sections(db: AsyncSession) -> Sequence[KbSection]:
    res = await db.execute(
        select(KbSection)
        .where(KbSection.parent_id.is_(None))
        .order_by(KbSection.sort_order)
    )
    return res.scalars().all()
