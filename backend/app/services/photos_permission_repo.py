from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photos import PhotoFolderPermission


async def list_folder_permissions(
    db: AsyncSession, folder_id: uuid.UUID
) -> Sequence[PhotoFolderPermission]:
    res = await db.execute(
        select(PhotoFolderPermission)
        .where(PhotoFolderPermission.folder_id == folder_id)
        .order_by(PhotoFolderPermission.created_at)
    )
    return res.scalars().all()


async def find_folder_permission(
    db: AsyncSession,
    *,
    folder_id: uuid.UUID,
    subject_type: str,
    subject_id: str,
) -> PhotoFolderPermission | None:
    res = await db.execute(
        select(PhotoFolderPermission).where(
            PhotoFolderPermission.folder_id == folder_id,
            PhotoFolderPermission.subject_type == subject_type,
            PhotoFolderPermission.subject_id == subject_id,
        )
    )
    return res.scalar_one_or_none()


async def delete_folder_permission(
    db: AsyncSession,
    *,
    folder_id: uuid.UUID,
    subject_id: str,
    subject_type: str | None,
) -> None:
    stmt = delete(PhotoFolderPermission).where(
        PhotoFolderPermission.folder_id == folder_id,
        PhotoFolderPermission.subject_id == subject_id,
    )
    if subject_type:
        stmt = stmt.where(PhotoFolderPermission.subject_type == subject_type)
    await db.execute(stmt)
