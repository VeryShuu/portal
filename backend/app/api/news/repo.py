"""Pure data-access helpers used by the news routers.

Keeps SQL out of the HTTP layer and lets the service code remain unaware of
HTTP concerns.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import NewsAttachment, NewsGalleryImage


async def list_gallery_images(
    db: AsyncSession, news_id: uuid.UUID
) -> Sequence[NewsGalleryImage]:
    res = await db.execute(
        select(NewsGalleryImage)
        .where(NewsGalleryImage.news_id == news_id)
        .order_by(NewsGalleryImage.sort_order, NewsGalleryImage.created_at)
    )
    return res.scalars().all()


async def reorder_gallery_images(
    db: AsyncSession,
    *,
    news_id: uuid.UUID,
    items: list[tuple[uuid.UUID, int]],
) -> None:
    for img_id, sort_order in items:
        await db.execute(
            update(NewsGalleryImage)
            .where(
                NewsGalleryImage.id == img_id,
                NewsGalleryImage.news_id == news_id,
            )
            .values(sort_order=sort_order)
        )
    await db.commit()


async def list_attachments(
    db: AsyncSession, news_id: uuid.UUID
) -> Sequence[NewsAttachment]:
    res = await db.execute(
        select(NewsAttachment)
        .where(NewsAttachment.news_id == news_id)
        .order_by(NewsAttachment.created_at)
    )
    return res.scalars().all()


async def get_attachment(
    db: AsyncSession, *, news_id: uuid.UUID, att_id: uuid.UUID
) -> NewsAttachment | None:
    res = await db.execute(
        select(NewsAttachment).where(
            NewsAttachment.id == att_id,
            NewsAttachment.news_id == news_id,
        )
    )
    return res.scalar_one_or_none()
