"""Data-access helpers for the files API package.

Keeps raw SQL (``select``/``text``) out of the HTTP route handlers.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import FileFolder, FileFolderPermission, FileItem, FileShare
from app.models.user import User


async def list_active_folders(db: AsyncSession) -> Sequence[FileFolder]:
    res = await db.execute(
        select(FileFolder).where(FileFolder.deleted_at.is_(None)).order_by(FileFolder.name)
    )
    return res.scalars().all()


async def find_active_folder_by_nc_path(db: AsyncSession, nc_path: str) -> FileFolder | None:
    res = await db.execute(
        select(FileFolder).where(FileFolder.nc_path == nc_path, FileFolder.deleted_at.is_(None))
    )
    return res.scalar_one_or_none()


async def cascade_descendant_paths(
    db: AsyncSession,
    *,
    old_nc_path: str,
    new_nc_path: str,
    now: datetime,
) -> None:
    """Переписывает денормализованный nc_path всех вложенных элементов после
    переименования/перемещения папки.

    Затрагивает дочерние file_folders, а также file_items и file_shares во всём
    поддереве. Совпадение по точному префиксу ``old_nc_path + '/'`` (через
    ``left()``), чтобы не зависеть от LIKE-метасимволов (``%``/``_``), которые
    допустимы в именах папок.
    """
    old_prefix = f"{old_nc_path}/"
    new_prefix = f"{new_nc_path}/"
    params = {
        "old_prefix": old_prefix,
        "new_prefix": new_prefix,
        "plen": len(old_prefix),
        "now": now,
    }
    await db.execute(
        text(
            "UPDATE file_folders"
            " SET nc_path = :new_prefix || substring(nc_path FROM :plen + 1),"
            "     updated_at = :now"
            " WHERE left(nc_path, :plen) = :old_prefix AND deleted_at IS NULL"
        ),
        params,
    )
    await db.execute(
        text(
            "UPDATE file_items"
            " SET nc_path = :new_prefix || substring(nc_path FROM :plen + 1)"
            " WHERE left(nc_path, :plen) = :old_prefix AND deleted_at IS NULL"
        ),
        params,
    )
    await db.execute(
        text(
            "UPDATE file_shares"
            " SET nc_path = :new_prefix || substring(nc_path FROM :plen + 1)"
            " WHERE left(nc_path, :plen) = :old_prefix AND revoked_at IS NULL"
        ),
        params,
    )


async def soft_delete_descendant_folders(
    db: AsyncSession, *, root_id: uuid.UUID, now: datetime
) -> None:
    await db.execute(
        text(
            "WITH RECURSIVE descendants AS ("
            "  SELECT id FROM file_folders"
            "  WHERE parent_id = :root_id AND deleted_at IS NULL"
            "  UNION ALL"
            "  SELECT f.id FROM file_folders f"
            "  JOIN descendants d ON f.parent_id = d.id"
            "  WHERE f.deleted_at IS NULL"
            ")"
            " UPDATE file_folders SET deleted_at = :now"
            " WHERE id IN (SELECT id FROM descendants)"
        ),
        {"root_id": root_id, "now": now},
    )


async def revoke_subtree_file_shares(
    db: AsyncSession, *, root_id: uuid.UUID, now: datetime
) -> None:
    await db.execute(
        text(
            "WITH RECURSIVE subtree AS ("
            "  SELECT id FROM file_folders WHERE id = :root_id"
            "  UNION ALL"
            "  SELECT f.id FROM file_folders f"
            "  JOIN subtree s ON f.parent_id = s.id"
            ")"
            " UPDATE file_shares SET revoked_at = :now"
            " WHERE folder_id IN (SELECT id FROM subtree)"
            "   AND revoked_at IS NULL"
        ),
        {"root_id": root_id, "now": now},
    )


async def find_active_file_item(
    db: AsyncSession, *, folder_id: uuid.UUID, name: str
) -> FileItem | None:
    res = await db.execute(
        select(FileItem).where(
            FileItem.folder_id == folder_id,
            FileItem.name == name,
            FileItem.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


async def list_active_file_items_by_names(
    db: AsyncSession, *, folder_id: uuid.UUID, names: Sequence[str]
) -> Sequence[FileItem]:
    res = await db.execute(
        select(FileItem).where(
            FileItem.folder_id == folder_id,
            FileItem.name.in_(names),
            FileItem.deleted_at.is_(None),
        )
    )
    return res.scalars().all()


async def list_folder_path_id_pairs(db: AsyncSession) -> Sequence[Any]:
    res = await db.execute(select(FileFolder.nc_path, FileFolder.id))
    return res.all()


async def insert_folder_if_absent(
    db: AsyncSession,
    *,
    new_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    name: str,
    nc_path: str,
    created_by: uuid.UUID,
    now: datetime,
) -> int:
    stmt = (
        pg_insert(FileFolder)
        .values(
            id=new_id,
            parent_id=parent_id,
            name=name,
            nc_path=nc_path,
            description=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        .on_conflict_do_nothing(index_elements=["nc_path"])
    )
    result = await db.execute(stmt)
    return int(cast(CursorResult, result).rowcount or 0)


async def insert_folder_permission_if_absent(
    db: AsyncSession,
    *,
    folder_id: uuid.UUID,
    subject_type: str,
    subject_id: str,
    subject_name: str | None,
    permission: str,
    granted_by: uuid.UUID,
    now: datetime,
) -> None:
    stmt = (
        pg_insert(FileFolderPermission)
        .values(
            id=uuid.uuid4(),
            folder_id=folder_id,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_name=subject_name,
            permission=permission,
            granted_by=granted_by,
            created_at=now,
        )
        .on_conflict_do_nothing()
    )
    await db.execute(stmt)


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def list_folder_permissions(
    db: AsyncSession, folder_id: uuid.UUID
) -> Sequence[FileFolderPermission]:
    res = await db.execute(
        select(FileFolderPermission).where(FileFolderPermission.folder_id == folder_id)
    )
    return res.scalars().all()


async def find_folder_permission_by_subject(
    db: AsyncSession, *, folder_id: uuid.UUID, subject_id: str
) -> FileFolderPermission | None:
    res = await db.execute(
        select(FileFolderPermission).where(
            FileFolderPermission.folder_id == folder_id,
            FileFolderPermission.subject_id == subject_id,
        )
    )
    return res.scalar_one_or_none()


async def find_folder_permission_by_id(
    db: AsyncSession, *, folder_id: uuid.UUID, perm_id: uuid.UUID
) -> FileFolderPermission | None:
    res = await db.execute(
        select(FileFolderPermission).where(
            FileFolderPermission.id == perm_id,
            FileFolderPermission.folder_id == folder_id,
        )
    )
    return res.scalar_one_or_none()


async def list_active_shares_for_file(
    db: AsyncSession, folder_id: uuid.UUID, filename: str
) -> list[FileShare]:
    res = await db.execute(
        select(FileShare).where(
            FileShare.folder_id == folder_id,
            FileShare.filename == filename,
            FileShare.revoked_at.is_(None),
        )
    )
    return list(res.scalars().all())


async def find_share_by_subject(
    db: AsyncSession, *, folder_id: uuid.UUID, filename: str, subject_id: str
) -> FileShare | None:
    res = await db.execute(
        select(FileShare).where(
            FileShare.folder_id == folder_id,
            FileShare.filename == filename,
            FileShare.subject_id == subject_id,
        )
    )
    return res.scalar_one_or_none()


async def find_share_by_id(
    db: AsyncSession, *, folder_id: uuid.UUID, filename: str, share_id: uuid.UUID
) -> FileShare | None:
    res = await db.execute(
        select(FileShare).where(
            FileShare.id == share_id,
            FileShare.folder_id == folder_id,
            FileShare.filename == filename,
        )
    )
    return res.scalar_one_or_none()


async def list_my_file_shares(
    db: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> Sequence[Any]:
    res = await db.execute(
        select(FileShare, FileFolder.name)
        .join(FileFolder, FileShare.folder_id == FileFolder.id)
        .where(
            FileShare.shared_by == user_id,
            FileShare.revoked_at.is_(None),
            FileFolder.deleted_at.is_(None),
            (FileShare.expires_at.is_(None)) | (FileShare.expires_at > now),
        )
        .order_by(FileShare.created_at.desc())
    )
    return res.all()


async def list_shares_for_subjects(
    db: AsyncSession, *, subject_ids: Sequence[str], now: datetime
) -> Sequence[Any]:
    res = await db.execute(
        select(FileShare, FileFolder.name, User.full_name)
        .join(FileFolder, FileShare.folder_id == FileFolder.id)
        .outerjoin(User, FileShare.shared_by == User.id)
        .where(
            FileShare.subject_id.in_(subject_ids),
            FileShare.revoked_at.is_(None),
            FileFolder.deleted_at.is_(None),
            (FileShare.expires_at.is_(None)) | (FileShare.expires_at > now),
        )
        .order_by(FileShare.created_at.desc())
    )
    return res.all()


async def admin_count_and_list_shares(
    db: AsyncSession,
    *,
    subject_id: str | None,
    folder_id: uuid.UUID | None,
    active_only: bool,
    limit: int,
    offset: int,
    now: datetime,
) -> tuple[int, Sequence[Any]]:
    conditions = []
    if subject_id:
        conditions.append(FileShare.subject_id == subject_id)
    if folder_id:
        conditions.append(FileShare.folder_id == folder_id)
    if active_only:
        conditions.append(FileShare.revoked_at.is_(None))
        conditions.append((FileShare.expires_at.is_(None)) | (FileShare.expires_at > now))

    count_stmt = select(func.count()).select_from(FileShare)
    for c in conditions:
        count_stmt = count_stmt.where(c)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(FileShare, FileFolder.name, User.full_name)
        .outerjoin(FileFolder, FileShare.folder_id == FileFolder.id)
        .outerjoin(User, FileShare.shared_by == User.id)
    )
    for c in conditions:
        stmt = stmt.where(c)
    stmt = stmt.order_by(FileShare.created_at.desc()).limit(limit).offset(offset)

    res = await db.execute(stmt)
    return int(total), res.all()
