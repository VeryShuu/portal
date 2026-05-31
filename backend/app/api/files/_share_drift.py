"""Keep file shares consistent when files are deleted/moved/renamed.

Used by files_ops.py (delete / bulk-delete / bulk-move) so that per-file
shares follow their file (sharing.md §10).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import FileShare
from app.services.files_acl import invalidate_file_share_cache
from app.services.files_shares_persistence import (
    ShareEntry,
    drop_file_shares,
    save_file_shares,
)


async def _persist_active(
    db: AsyncSession, folder_id: uuid.UUID, filename: str, nc_path: str
) -> None:
    res = await db.execute(
        select(FileShare).where(
            FileShare.folder_id == folder_id,
            FileShare.filename == filename,
            FileShare.revoked_at.is_(None),
        )
    )
    active = list(res.scalars().all())
    if not active:
        await drop_file_shares(nc_path)
        return
    entries = [
        ShareEntry(
            subject_type=s.subject_type,
            subject_id=s.subject_id,
            subject_name=s.subject_name,
            permission=s.permission,
            expires_at=s.expires_at.isoformat() if s.expires_at else None,
        )
        for s in active
    ]
    await save_file_shares(nc_path, entries)


async def revoke_file_shares(
    db: AsyncSession,
    redis: Redis,
    *,
    folder_id: uuid.UUID,
    filename: str,
    nc_path: str,
) -> None:
    """Soft-revoke all active shares for a deleted file and drop its json entry.

    Commits its own changes. The caller must have committed the file deletion
    first (or be in a state where committing shares is safe).
    """
    res = await db.execute(
        select(FileShare).where(
            FileShare.folder_id == folder_id,
            FileShare.filename == filename,
            FileShare.revoked_at.is_(None),
        )
    )
    active = list(res.scalars().all())
    if active:
        now = datetime.now(UTC)
        for s in active:
            s.revoked_at = now
        await db.commit()
    await invalidate_file_share_cache(redis, folder_id, filename)
    await drop_file_shares(nc_path)


async def move_file_shares(
    db: AsyncSession,
    redis: Redis,
    *,
    src_folder_id: uuid.UUID,
    src_filename: str,
    src_nc_path: str,
    dst_folder_id: uuid.UUID,
    dst_filename: str,
    dst_nc_path: str,
) -> None:
    """Repoint active shares of a moved/renamed file to its new location.

    Commits its own changes.
    """
    res = await db.execute(
        select(FileShare).where(
            FileShare.folder_id == src_folder_id,
            FileShare.filename == src_filename,
            FileShare.revoked_at.is_(None),
        )
    )
    active = list(res.scalars().all())
    if not active:
        return
    for s in active:
        s.folder_id = dst_folder_id
        s.filename = dst_filename
        s.nc_path = dst_nc_path
    await db.commit()

    await invalidate_file_share_cache(redis, src_folder_id, src_filename)
    await invalidate_file_share_cache(redis, dst_folder_id, dst_filename)
    await drop_file_shares(src_nc_path)
    await _persist_active(db, dst_folder_id, dst_filename, dst_nc_path)
