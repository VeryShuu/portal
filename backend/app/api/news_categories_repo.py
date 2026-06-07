"""Pure data-access helpers for news categories.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
The category registry itself lives in a JSON file; only the denormalised
``News.categories`` array operations touch the database.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import News


async def count_news_by_category(db: AsyncSession) -> list[tuple[str, int]]:
    result = await db.execute(
        select(
            func.unnest(News.categories).label("cat"),
            func.count().label("cnt"),
        )
        .where(News.deleted_at.is_(None))
        .group_by("cat")
    )
    return [(row.cat, row.cnt) for row in result]


async def rename_category_in_news(
    db: AsyncSession, *, old_name: str, new_name: str
) -> None:
    await db.execute(
        update(News)
        .where(News.deleted_at.is_(None))
        .where(func.array_position(News.categories, old_name).is_not(None))
        .values(categories=func.array_replace(News.categories, old_name, new_name))
    )


async def remove_category_from_news(db: AsyncSession, *, name: str) -> None:
    await db.execute(
        update(News)
        .where(News.deleted_at.is_(None))
        .where(func.array_position(News.categories, name).is_not(None))
        .values(categories=func.array_remove(News.categories, name))
    )
