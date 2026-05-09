"""KB service — бизнес-логика."""

from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import VIEW_DEDUP_TTL_SECONDS
from app.core.text import slugify as _slugify_common
from app.models.kb import KbArticle, KbArticleTag, KbTag


def _slugify(text_: str) -> str:
    return _slugify_common(text_, fallback="section")


async def record_article_view(
    db: AsyncSession,
    redis: Redis,
    article_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Increment view_count with per-user deduplication.

    Returns True when the view was counted, False when deduplicated.
    """
    view_key = f"kb:view:{article_id}:{user_id}"
    if await redis.get(view_key):
        return False
    await db.execute(
        update(KbArticle)
        .where(KbArticle.id == article_id)
        .values(view_count=KbArticle.view_count + 1)
    )
    await db.commit()
    await redis.setex(view_key, VIEW_DEDUP_TTL_SECONDS, "1")
    return True


async def _resolve_tags(db: AsyncSession, tag_names: list[str]) -> list[KbTag]:
    if not tag_names:
        return []
    slugs = [_slugify(n) for n in tag_names]
    result = await db.execute(select(KbTag).where(KbTag.slug.in_(slugs)))
    existing: dict[str, KbTag] = {t.slug: t for t in result.scalars()}
    tags: list[KbTag] = []
    for name, slug in zip(tag_names, slugs, strict=False):
        tag = existing.get(slug)
        if not tag:
            tag = KbTag(name=name.strip(), slug=slug)
            db.add(tag)
            await db.flush()
            existing[slug] = tag
        tags.append(tag)
    return tags


async def set_article_tags(
    db: AsyncSession,
    article: KbArticle,
    tag_names: list[str],
) -> None:
    """Replace all tags on an article."""
    await db.execute(delete(KbArticleTag).where(KbArticleTag.article_id == article.id))
    tags = await _resolve_tags(db, tag_names)
    for tag in tags:
        db.add(KbArticleTag(article_id=article.id, tag_id=tag.id))
