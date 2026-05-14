from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photos import Photo, PhotoFolder, PhotoTagAssignment


async def fetch_active_photo(db: AsyncSession, photo_id: uuid.UUID) -> Photo | None:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    return res.scalar_one_or_none()


async def fetch_photo_any(db: AsyncSession, photo_id: uuid.UUID) -> Photo | None:
    res = await db.execute(select(Photo).where(Photo.id == photo_id))
    return res.scalar_one_or_none()


async def fetch_folder(db: AsyncSession, folder_id: uuid.UUID) -> PhotoFolder | None:
    return await db.scalar(select(PhotoFolder).where(PhotoFolder.id == folder_id))


async def fetch_active_folder(db: AsyncSession, folder_id: uuid.UUID) -> PhotoFolder | None:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    return res.scalar_one_or_none()


def _folder_photos_filtered_query(
    folder_id: uuid.UUID,
    *,
    min_date: datetime | None,
    max_date: datetime | None,
    min_size: int | None,
    max_size: int | None,
    mime_type: str | None,
):
    base = select(Photo).where(Photo.folder_id == folder_id, Photo.deleted_at.is_(None))
    if min_date is not None:
        base = base.where(Photo.taken_at.isnot(None), Photo.taken_at >= min_date)
    if max_date is not None:
        base = base.where(Photo.taken_at.isnot(None), Photo.taken_at <= max_date)
    if min_size is not None:
        base = base.where(Photo.size_bytes >= min_size)
    if max_size is not None:
        base = base.where(Photo.size_bytes <= max_size)
    if mime_type is not None:
        base = base.where(Photo.mime_type == mime_type)
    return base


async def count_folder_photos(
    db: AsyncSession,
    folder_id: uuid.UUID,
    *,
    min_date: datetime | None,
    max_date: datetime | None,
    min_size: int | None,
    max_size: int | None,
    mime_type: str | None,
) -> int:
    base = _folder_photos_filtered_query(
        folder_id,
        min_date=min_date,
        max_date=max_date,
        min_size=min_size,
        max_size=max_size,
        mime_type=mime_type,
    )
    return int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)


async def fetch_folder_photos_page(
    db: AsyncSession,
    folder_id: uuid.UUID,
    *,
    sort: str,
    min_date: datetime | None,
    max_date: datetime | None,
    min_size: int | None,
    max_size: int | None,
    mime_type: str | None,
    offset: int,
    limit: int,
) -> Sequence[Photo]:
    sort_col = {
        "created_at": Photo.created_at,
        "taken_at": Photo.taken_at,
        "original_name": Photo.original_name,
    }[sort]
    base = _folder_photos_filtered_query(
        folder_id,
        min_date=min_date,
        max_date=max_date,
        min_size=min_size,
        max_size=max_size,
        mime_type=mime_type,
    )
    order = sort_col.desc().nullslast() if sort != "original_name" else sort_col.asc()
    res = await db.execute(base.order_by(order).offset(offset).limit(limit))
    return res.scalars().all()


async def count_deleted_photos_admin(db: AsyncSession, cutoff: datetime) -> int:
    base_cond = [Photo.deleted_at.isnot(None), Photo.deleted_at > cutoff]
    count_q = select(func.count()).select_from(
        select(Photo)
        .join(PhotoFolder, Photo.folder_id == PhotoFolder.id, isouter=True)
        .where(*base_cond)
        .subquery()
    )
    return int(await db.scalar(count_q) or 0)


async def fetch_deleted_photos_admin_page(
    db: AsyncSession, cutoff: datetime, *, offset: int, limit: int
) -> list[tuple[Photo, PhotoFolder | None]]:
    base_cond = [Photo.deleted_at.isnot(None), Photo.deleted_at > cutoff]
    stmt = (
        select(Photo, PhotoFolder)
        .join(PhotoFolder, Photo.folder_id == PhotoFolder.id, isouter=True)
        .where(*base_cond)
        .order_by(Photo.deleted_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def fetch_deleted_photos_with_folders(
    db: AsyncSession, cutoff: datetime, limit: int = 2000
) -> list[tuple[Photo, PhotoFolder | None]]:
    res = await db.execute(
        select(Photo, PhotoFolder)
        .join(PhotoFolder, Photo.folder_id == PhotoFolder.id, isouter=True)
        .where(Photo.deleted_at.isnot(None), Photo.deleted_at > cutoff)
        .order_by(Photo.deleted_at.desc())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in res.all()]


async def fetch_recent_photos_with_folders(
    db: AsyncSession, limit: int
) -> list[tuple[Photo, PhotoFolder]]:
    res = await db.execute(
        select(Photo, PhotoFolder)
        .join(PhotoFolder, Photo.folder_id == PhotoFolder.id)
        .where(
            Photo.deleted_at.is_(None),
            PhotoFolder.deleted_at.is_(None),
            Photo.processed.is_(True),
        )
        .order_by(Photo.created_at.desc())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in res.all()]


async def fetch_storage_stats_top_folders(
    db: AsyncSession, limit: int = 50
) -> list[tuple[uuid.UUID, str, str, int, int]]:
    res = await db.execute(
        select(
            PhotoFolder.id,
            PhotoFolder.name,
            PhotoFolder.path,
            func.coalesce(func.sum(Photo.size_bytes), 0).label("size_bytes"),
            func.count(Photo.id).label("file_count"),
        )
        .join(Photo, Photo.folder_id == PhotoFolder.id)
        .where(Photo.deleted_at.is_(None), PhotoFolder.deleted_at.is_(None))
        .group_by(PhotoFolder.id, PhotoFolder.name, PhotoFolder.path)
        .order_by(func.sum(Photo.size_bytes).desc())
        .limit(limit)
    )
    return [(row[0], row[1], row[2], int(row[3]), int(row[4])) for row in res.all()]


async def fetch_active_photos_map(
    db: AsyncSession, photo_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Photo]:
    photos_res = await db.execute(
        select(Photo).where(Photo.id.in_(photo_ids), Photo.deleted_at.is_(None))
    )
    return {p.id: p for p in photos_res.scalars().all()}


async def fetch_folders_map(
    db: AsyncSession, folder_ids: set[uuid.UUID]
) -> dict[uuid.UUID, PhotoFolder]:
    if not folder_ids:
        return {}
    folders_res = await db.execute(select(PhotoFolder).where(PhotoFolder.id.in_(folder_ids)))
    return {f.id: f for f in folders_res.scalars().all()}


async def purge_photo_row(db: AsyncSession, photo_id: uuid.UUID) -> None:
    await db.execute(delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == photo_id))
    await db.execute(delete(Photo).where(Photo.id == photo_id))
