"""Files module ACL service.

Permission levels: viewer < editor < manager
Subject types: user | group

Resolution algorithm for a folder:
  1. portal admin          → 'manager'
  2. created_by = user     → 'manager'
  3. direct permission on this folder (user or group match)
  4. recurse to parent_id
  5. None → no access → 403
"""

from __future__ import annotations

import contextlib
import uuid

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.files import FileFolder
from app.models.user import User
from app.services.acl_base import subject_ids_for_user as _subject_ids_for_user

logger = get_logger(__name__)

_PERM_RANK = {"viewer": 1, "editor": 2, "manager": 3}
_ACL_TTL = 300


def perm_gte(actual: str | None, required: str) -> bool:
    if actual is None:
        return False
    return _PERM_RANK.get(actual, 0) >= _PERM_RANK.get(required, 99)


def _cache_key(user_id: uuid.UUID, folder_id: uuid.UUID) -> str:
    return f"files_acl:{user_id}:folder:{folder_id}"


async def _get_cached(redis: Redis, key: str) -> str | None:
    try:
        return await redis.get(key)
    except Exception:
        return None


async def _set_cached(redis: Redis, key: str, value: str) -> None:
    with contextlib.suppress(Exception):
        await redis.setex(key, _ACL_TTL, value)


async def _scan_and_delete(redis: Redis, pattern: str, batch: int = 500) -> None:
    keys_buf: list[str] = []
    async for key in redis.scan_iter(match=pattern, count=batch):
        keys_buf.append(key)
        if len(keys_buf) >= batch:
            await redis.delete(*keys_buf)
            keys_buf.clear()
    if keys_buf:
        await redis.delete(*keys_buf)


async def invalidate_folder_cache(
    redis: Redis, folder_id: uuid.UUID, db: AsyncSession | None = None
) -> None:
    try:
        await _scan_and_delete(redis, f"files_acl:*:folder:{folder_id}")
        if db is not None:
            from sqlalchemy import text

            result = await db.execute(
                text(
                    """
                    WITH RECURSIVE descendants AS (
                        SELECT id FROM file_folders WHERE id = :fid
                        UNION ALL
                        SELECT f.id FROM file_folders f
                        JOIN descendants d ON f.parent_id = d.id
                        WHERE f.deleted_at IS NULL
                    )
                    SELECT id FROM descendants WHERE id != :fid
                    """
                ),
                {"fid": folder_id},
            )
            for (child_id,) in result.fetchall():
                await _scan_and_delete(redis, f"files_acl:*:folder:{child_id}")
    except Exception:
        pass


async def invalidate_user_cache(redis: Redis, user_id: uuid.UUID) -> None:
    with contextlib.suppress(Exception):
        await _scan_and_delete(redis, f"files_acl:{user_id}:folder:*")


async def _resolve_via_cte(
    db: AsyncSession, folder_id: uuid.UUID, subject_ids: list[str]
) -> str | None:
    """Один рекурсивный CTE-запрос: все предки + их права за один SELECT."""
    if not subject_ids:
        return None
    result = await db.execute(
        text("""
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, 0 AS depth
                FROM file_folders WHERE id = :folder_id AND deleted_at IS NULL
                UNION ALL
                SELECT f.id, f.parent_id, a.depth + 1
                FROM file_folders f JOIN ancestors a ON f.id = a.parent_id
                WHERE a.depth < 20 AND f.deleted_at IS NULL
            )
            SELECT p.permission
            FROM ancestors a
            JOIN file_folder_permissions p ON p.folder_id = a.id
            WHERE p.subject_id = ANY(:sids)
            ORDER BY CASE p.permission
                WHEN 'manager' THEN 3
                WHEN 'editor'  THEN 2
                WHEN 'viewer'  THEN 1
                ELSE 0 END DESC
            LIMIT 1
        """),
        {"folder_id": str(folder_id), "sids": subject_ids},
    )
    row = result.fetchone()
    return row[0] if row else None


async def resolve_folder_permission(
    user: User,
    folder: FileFolder,
    db: AsyncSession,
    redis: Redis,
) -> str | None:
    """Return best permission for user on folder, traversing up to ancestors."""
    if user.role == "admin":
        return "manager"
    if folder.created_by == user.id:
        return "manager"

    cache_key = _cache_key(user.id, folder.id)
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached if cached != "none" else None

    subject_ids = await _subject_ids_for_user(user)
    best = await _resolve_via_cte(db, folder.id, subject_ids)

    await _set_cached(redis, cache_key, best if best else "none")
    return best


async def require_folder_permission(
    user: User,
    folder: FileFolder,
    required: str,
    db: AsyncSession,
    redis: Redis,
) -> None:
    perm = await resolve_folder_permission(user, folder, db, redis)
    if not perm_gte(perm, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient file permissions",
        )


async def filter_accessible_folders(
    user: User,
    folders: list[FileFolder],
    db: AsyncSession,
    redis: Redis,
    min_perm: str = "viewer",
) -> list[tuple[FileFolder, str]]:
    """Return [(folder, permission)] for folders user has at least min_perm on."""
    if user.role == "admin":
        return [(f, "manager") for f in folders]
    result = []
    for f in folders:
        perm = await resolve_folder_permission(user, f, db, redis)
        if perm_gte(perm, min_perm):
            assert perm is not None
            result.append((f, perm))
    return result
