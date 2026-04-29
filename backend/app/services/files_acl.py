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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.files import FileFolder, FileFolderPermission
from app.models.user import User

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


def _subject_ids_for_user(user: User) -> list[str]:
    ids: list[str] = [str(user.id)]
    if user.keycloak_id:
        ids.append(user.keycloak_id)
    groups = getattr(user, "keycloak_groups", None)
    if groups and isinstance(groups, list):
        ids.extend(str(g) for g in groups)
    return ids


async def _direct_permission_for_folder(
    db: AsyncSession, folder_id: uuid.UUID, subject_ids: list[str]
) -> str | None:
    if not subject_ids:
        return None
    result = await db.execute(
        select(FileFolderPermission.permission).where(
            FileFolderPermission.folder_id == folder_id,
            FileFolderPermission.subject_id.in_(subject_ids),
        )
    )
    perms = [row[0] for row in result.fetchall()]
    if not perms:
        return None
    return max(perms, key=lambda p: _PERM_RANK.get(p, 0))


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

    subject_ids = _subject_ids_for_user(user)
    best: str | None = None

    current_id: uuid.UUID | None = folder.id
    visited: set[uuid.UUID] = set()
    depth = 0

    while current_id and depth < 20:
        if current_id in visited:
            break
        visited.add(current_id)

        perm = await _direct_permission_for_folder(db, current_id, subject_ids)
        if perm and _PERM_RANK.get(perm, 0) > _PERM_RANK.get(best or "", 0):
            best = perm

        if best == "manager":
            break

        res = await db.execute(
            select(FileFolder).where(
                FileFolder.id == current_id,
                FileFolder.deleted_at.is_(None),
            )
        )
        f = res.scalar_one_or_none()
        if not f:
            break
        current_id = f.parent_id
        depth += 1

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
            result.append((f, perm))
    return result
