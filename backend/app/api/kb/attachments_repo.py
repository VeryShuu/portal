"""Pure data-access helpers for KB article file attachments.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticleFile


async def list_files(
    db: AsyncSession, article_id: uuid.UUID
) -> Sequence[KbArticleFile]:
    res = await db.execute(
        select(KbArticleFile)
        .where(KbArticleFile.article_id == article_id)
        .order_by(KbArticleFile.created_at)
    )
    return res.scalars().all()


async def get_file_uploader(
    db: AsyncSession, file_id: uuid.UUID
) -> uuid.UUID | None:
    res = await db.execute(
        select(KbArticleFile.uploaded_by).where(KbArticleFile.id == file_id)
    )
    row = res.fetchone()
    return row[0] if row else None


async def get_file(
    db: AsyncSession, *, article_id: uuid.UUID, file_id: uuid.UUID
) -> KbArticleFile | None:
    res = await db.execute(
        select(KbArticleFile).where(
            KbArticleFile.id == file_id,
            KbArticleFile.article_id == article_id,
        )
    )
    return res.scalar_one_or_none()


async def get_file_by_name(
    db: AsyncSession, *, article_id: uuid.UUID, filename: str
) -> KbArticleFile | None:
    res = await db.execute(
        select(KbArticleFile).where(
            KbArticleFile.article_id == article_id,
            KbArticleFile.filename == filename,
        )
    )
    return res.scalar_one_or_none()
