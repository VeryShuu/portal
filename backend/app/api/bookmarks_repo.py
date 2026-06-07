"""Pure data-access helpers for bookmarks.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
Each helper performs exactly one ``db.execute`` so the calling routes preserve
their original query ordering.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import case, func, select, text
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.links import Bookmark


async def list_user_bookmarks(
    db: AsyncSession, user_id: uuid.UUID
) -> Sequence[Bookmark]:
    res = await db.execute(
        select(Bookmark)
        .where(Bookmark.user_id == user_id)
        .order_by(Bookmark.sort_order, Bookmark.created_at)
    )
    return res.scalars().all()


async def count_user_bookmarks(db: AsyncSession, user_id: uuid.UUID) -> int:
    res = await db.execute(
        select(func.count()).select_from(Bookmark).where(Bookmark.user_id == user_id)
    )
    return res.scalar_one()


async def acquire_user_lock(db: AsyncSession, *, namespace: int, key: int) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :k)"),
        {"ns": namespace, "k": key},
    )


async def max_sort_order(db: AsyncSession, user_id: uuid.UUID) -> int:
    res = await db.execute(
        select(func.coalesce(func.max(Bookmark.sort_order), 0)).where(
            Bookmark.user_id == user_id
        )
    )
    return res.scalar_one()


async def get_user_bookmark(
    db: AsyncSession, *, bookmark_id: uuid.UUID, user_id: uuid.UUID
) -> Bookmark | None:
    res = await db.execute(
        select(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.user_id == user_id)
    )
    return res.scalar_one_or_none()


async def list_user_bookmark_ids(
    db: AsyncSession, user_id: uuid.UUID
) -> set[uuid.UUID]:
    res = await db.execute(select(Bookmark.id).where(Bookmark.user_id == user_id))
    return {row[0] for row in res.all()}


async def apply_reorder(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    items: list[tuple[uuid.UUID, int]],
) -> None:
    when_clauses = [(Bookmark.id == bid, sort_order) for bid, sort_order in items]
    sort_case = case(*when_clauses, else_=Bookmark.sort_order)
    await db.execute(
        sa_update(Bookmark)
        .where(
            Bookmark.id.in_([bid for bid, _ in items]),
            Bookmark.user_id == user_id,
        )
        .values(sort_order=sort_case)
    )
