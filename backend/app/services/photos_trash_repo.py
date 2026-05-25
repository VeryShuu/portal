"""Trash-specific DB queries.

Выделено из ``photos_trash.py`` для разделения ответственностей
(см. ревью, находка #7: repo / file-service / orchestrator).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photos import Photo, PhotoFolder, PhotoTagAssignment


async def fetch_expired_photos(
    db: AsyncSession, cutoff: datetime
) -> list[Photo]:
    res = await db.execute(
        select(Photo).where(Photo.deleted_at.isnot(None), Photo.deleted_at < cutoff)
    )
    return list(res.scalars().all())


async def fetch_all_trashed_photos(db: AsyncSession) -> list[Photo]:
    res = await db.execute(select(Photo).where(Photo.deleted_at.isnot(None)))
    return list(res.scalars().all())


async def fetch_expired_root_folders(
    db: AsyncSession, cutoff: datetime
) -> Sequence[PhotoFolder]:
    res = await db.execute(
        select(PhotoFolder).where(
            PhotoFolder.deleted_at.isnot(None),
            PhotoFolder.deleted_at < cutoff,
            PhotoFolder.parent_id.is_(None),
        )
    )
    return res.scalars().all()


async def fetch_expired_non_root_folders(
    db: AsyncSession, cutoff: datetime
) -> Sequence[PhotoFolder]:
    res = await db.execute(
        select(PhotoFolder).where(
            PhotoFolder.deleted_at.isnot(None),
            PhotoFolder.deleted_at < cutoff,
            PhotoFolder.parent_id.isnot(None),
        )
    )
    return res.scalars().all()


async def fetch_active_folder_ids(db: AsyncSession) -> set[uuid.UUID]:
    res = await db.execute(
        select(PhotoFolder.id).where(PhotoFolder.deleted_at.is_(None))
    )
    return {row[0] for row in res.all()}


async def fetch_all_trashed_folders(db: AsyncSession) -> Sequence[PhotoFolder]:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.deleted_at.isnot(None))
    )
    return res.scalars().all()


async def delete_folder_row(db: AsyncSession, folder_id: uuid.UUID) -> None:
    await db.execute(delete(PhotoFolder).where(PhotoFolder.id == folder_id))


async def purge_photo_row(db: AsyncSession, photo_id: uuid.UUID) -> None:
    """Удаляет строку Photo и её tag-assignments. Без commit."""
    await db.execute(
        delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == photo_id)
    )
    await db.execute(delete(Photo).where(Photo.id == photo_id))


__all__ = [
    "fetch_expired_photos",
    "fetch_all_trashed_photos",
    "fetch_expired_root_folders",
    "fetch_expired_non_root_folders",
    "fetch_active_folder_ids",
    "fetch_all_trashed_folders",
    "delete_folder_row",
    "purge_photo_row",
]
