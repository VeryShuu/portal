from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photos import PhotoTag, PhotoTagAssignment


async def list_tags_with_usage(db: AsyncSession, q: str) -> Sequence[Any]:
    stmt = (
        select(PhotoTag, func.count(PhotoTagAssignment.photo_id).label("usage_count"))
        .outerjoin(PhotoTagAssignment, PhotoTagAssignment.tag_id == PhotoTag.id)
        .group_by(PhotoTag.id)
        .order_by(PhotoTag.name)
    )
    if q:
        stmt = stmt.where(PhotoTag.name.ilike(f"%{q}%"))
    res = await db.execute(stmt)
    return res.all()


async def find_tag_by_name(db: AsyncSession, name: str) -> PhotoTag | None:
    tag: PhotoTag | None = await db.scalar(select(PhotoTag).where(PhotoTag.name == name))
    return tag


async def get_tag(db: AsyncSession, tag_id: uuid.UUID) -> PhotoTag | None:
    tag: PhotoTag | None = await db.scalar(select(PhotoTag).where(PhotoTag.id == tag_id))
    return tag


async def delete_tag(db: AsyncSession, tag_id: uuid.UUID) -> None:
    await db.execute(delete(PhotoTag).where(PhotoTag.id == tag_id))


async def list_photo_tags(
    db: AsyncSession, photo_id: uuid.UUID
) -> Sequence[PhotoTag]:
    res = await db.execute(
        select(PhotoTag)
        .join(PhotoTagAssignment, PhotoTagAssignment.tag_id == PhotoTag.id)
        .where(PhotoTagAssignment.photo_id == photo_id)
        .order_by(PhotoTag.name)
    )
    return res.scalars().all()


async def clear_photo_tags(db: AsyncSession, photo_id: uuid.UUID) -> None:
    await db.execute(
        delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == photo_id)
    )
