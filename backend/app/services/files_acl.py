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
import hashlib
import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import FileFolder
from app.models.user import User
from app.services.acl_base import (
    ACL_TTL as _ACL_TTL,
)
from app.services.acl_base import (
    get_cached as _get_cached,
)
from app.services.acl_base import (
    scan_and_delete as _scan_and_delete,
)
from app.services.acl_base import (
    set_cached as _set_cached,
)
from app.services.acl_base import (
    subject_ids_for_user as _subject_ids_for_user,
)

logger = logging.getLogger(__name__)

_PERM_RANK = {"viewer": 1, "editor": 2, "manager": 3}

_MAX_FOLDER_DEPTH = 20


def perm_gte(actual: str | None, required: str) -> bool:
    if actual is None:
        return False
    return _PERM_RANK.get(actual, 0) >= _PERM_RANK.get(required, 99)


def _cache_key(user_id: uuid.UUID, folder_id: uuid.UUID) -> str:
    return f"files_acl:{user_id}:folder:{folder_id}"


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
        logger.warning(
            "Failed to invalidate files ACL cache for folder %s and its descendants",
            folder_id,
            exc_info=True,
        )


async def invalidate_user_cache(redis: Redis, user_id: uuid.UUID) -> None:
    with contextlib.suppress(Exception):
        await _scan_and_delete(redis, f"files_acl:{user_id}:folder:*")


async def _resolve_via_cte(
    db: AsyncSession, folder_id: uuid.UUID, subject_ids: list[str]
) -> str | None:
    """Один рекурсивный CTE-запрос: все предки + их права за один SELECT.

    Рекурсия останавливается на папке с inherit_permissions = FALSE:
    текущая папка всегда включается, но дальше вверх подъём не идёт.
    """
    if not subject_ids:
        return None
    result = await db.execute(
        text(f"""
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, inherit_permissions, 0 AS depth
                FROM file_folders WHERE id = :folder_id AND deleted_at IS NULL
                UNION ALL
                SELECT f.id, f.parent_id, f.inherit_permissions, a.depth + 1
                FROM file_folders f JOIN ancestors a ON f.id = a.parent_id
                WHERE a.inherit_permissions = TRUE
                  AND a.depth < {_MAX_FOLDER_DEPTH}
                  AND f.deleted_at IS NULL
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


def _partition_cached_folders(
    folders: list[FileFolder],
    cached_values: list[str | None],
    user_id: uuid.UUID,
    result: dict[uuid.UUID, str | None],
) -> list[uuid.UUID]:
    """Split folders into resolved (owner/cache hit) vs cache-miss IDs.

    Resolved entries are written into ``result``; miss IDs are returned.
    """
    uncached_ids: list[uuid.UUID] = []
    for folder, cached in zip(folders, cached_values, strict=False):
        if folder.created_by == user_id:
            result[folder.id] = "manager"
        elif cached is not None:
            result[folder.id] = cached if cached != "none" else None
        else:
            uncached_ids.append(folder.id)
    return uncached_ids


async def _resolve_folders_via_cte(
    db: AsyncSession, uncached_ids: list[uuid.UUID], subject_ids: list[str]
) -> dict[uuid.UUID, list[str]]:
    """One recursive CTE: all matching permissions per root folder."""
    db_result = await db.execute(
        text(f"""
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, inherit_permissions,
                       id AS root_id, 0 AS depth
                FROM file_folders
                WHERE id = ANY(:root_ids) AND deleted_at IS NULL
                UNION ALL
                SELECT f.id, f.parent_id, f.inherit_permissions,
                       a.root_id, a.depth + 1
                FROM file_folders f
                JOIN ancestors a ON f.id = a.parent_id
                WHERE a.inherit_permissions = TRUE
                  AND a.depth < {_MAX_FOLDER_DEPTH}
                  AND f.deleted_at IS NULL
            )
            SELECT a.root_id, p.permission
            FROM ancestors a
            JOIN file_folder_permissions p ON p.folder_id = a.id
            WHERE p.subject_id = ANY(:sids)
        """),
        {"root_ids": [str(fid) for fid in uncached_ids], "sids": subject_ids},
    )

    perms_by_root: dict[uuid.UUID, list[str]] = {fid: [] for fid in uncached_ids}
    for row in db_result.fetchall():
        root_id = uuid.UUID(str(row[0]))
        if root_id in perms_by_root:
            perms_by_root[root_id].append(row[1])
    return perms_by_root


async def _write_folder_perm_cache(redis: Redis, pipe_data: list[tuple[str, str]]) -> None:
    """Write resolved (key, value) permission pairs back via a Redis pipeline."""
    try:
        async with redis.pipeline(transaction=False) as pipe:
            for key, val in pipe_data:
                pipe.setex(key, _ACL_TTL, val)
            await pipe.execute()
    except Exception:
        pass


async def batch_resolve_folder_permissions(
    user: User,
    folders: list[FileFolder],
    db: AsyncSession,
    redis: Redis,
) -> dict[uuid.UUID, str | None]:
    """Return {folder_id: best_permission} for all folders in a single pass.

    Algorithm:
    1. Return 'manager' for admins — no DB hit.
    2. Check Redis cache via MGET (one round-trip).
    3. For uncached folders, fetch all matching permissions across the full
       ancestor tree in a single SQL query; resolve inheritance in Python using
       the already-loaded folder list as an in-memory adjacency map.
    4. Write resolved values back to Redis cache.
    """
    if user.role == "admin":
        return {f.id: "manager" for f in folders}

    if not folders:
        return {}

    result: dict[uuid.UUID, str | None] = {}

    cache_keys = [_cache_key(user.id, f.id) for f in folders]
    try:
        cached_values: list[str | None] = await redis.mget(*cache_keys)
    except Exception:
        cached_values = [None] * len(folders)

    uncached_ids = _partition_cached_folders(folders, cached_values, user.id, result)
    if not uncached_ids:
        return result

    subject_ids = await _subject_ids_for_user(user)
    if not subject_ids:
        for fid in uncached_ids:
            result[fid] = None
        return result

    perms_by_root = await _resolve_folders_via_cte(db, uncached_ids, subject_ids)

    pipe_data: list[tuple[str, str]] = []
    for fid in uncached_ids:
        perms = perms_by_root.get(fid, [])
        best = max(perms, key=lambda p: _PERM_RANK.get(p, 0)) if perms else None
        result[fid] = best
        pipe_data.append((_cache_key(user.id, fid), best if best else "none"))

    await _write_folder_perm_cache(redis, pipe_data)
    return result


# ── Per-file shares (sharing.md) ────────────────────────────────────────────────


def _filename_hash(filename: str) -> str:
    return hashlib.sha1(filename.encode("utf-8")).hexdigest()[:16]


def _file_share_cache_key(user_id: uuid.UUID, folder_id: uuid.UUID, filename: str) -> str:
    return f"files_share:{user_id}:{folder_id}:{_filename_hash(filename)}"


async def invalidate_file_share_cache(redis: Redis, folder_id: uuid.UUID, filename: str) -> None:
    with contextlib.suppress(Exception):
        await _scan_and_delete(redis, f"files_share:*:{folder_id}:{_filename_hash(filename)}")


async def invalidate_file_share_user_cache(redis: Redis, user_id: uuid.UUID) -> None:
    with contextlib.suppress(Exception):
        await _scan_and_delete(redis, f"files_share:{user_id}:*")


async def invalidate_file_share_folder_cache(
    redis: Redis, folder_id: uuid.UUID, db: AsyncSession | None = None
) -> None:
    """Drop file-share cache for a folder and (optionally) all its descendants.

    Used on folder delete (F5): shares of every file under the subtree are
    revoked, so their cached permissions must be flushed across all users.
    """
    try:
        await _scan_and_delete(redis, f"files_share:*:{folder_id}:*")
        if db is not None:
            result = await db.execute(
                text(
                    """
                    WITH RECURSIVE descendants AS (
                        SELECT id FROM file_folders WHERE id = :fid
                        UNION ALL
                        SELECT f.id FROM file_folders f
                        JOIN descendants d ON f.parent_id = d.id
                    )
                    SELECT id FROM descendants WHERE id != :fid
                    """
                ),
                {"fid": folder_id},
            )
            for (child_id,) in result.fetchall():
                await _scan_and_delete(redis, f"files_share:*:{child_id}:*")
    except Exception:
        logger.warning(
            "Failed to invalidate file-share cache for folder %s and descendants",
            folder_id,
            exc_info=True,
        )


async def resolve_file_share_permission(
    user: User,
    folder_id: uuid.UUID,
    filename: str,
    db: AsyncSession,
    redis: Redis,
) -> str | None:
    """Return best active file-share permission (viewer|editor) for user on a file."""
    cache_key = _file_share_cache_key(user.id, folder_id, filename)
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached if cached != "none" else None

    subject_ids = await _subject_ids_for_user(user)
    best: str | None = None
    if subject_ids:
        result = await db.execute(
            text("""
                SELECT permission
                FROM file_shares
                WHERE folder_id = :folder_id
                  AND filename = :filename
                  AND subject_id = ANY(:sids)
                  AND revoked_at IS NULL
                  AND (expires_at IS NULL OR expires_at > :now)
                ORDER BY CASE permission
                    WHEN 'editor' THEN 2
                    WHEN 'viewer' THEN 1
                    ELSE 0 END DESC
                LIMIT 1
            """),
            {
                "folder_id": str(folder_id),
                "filename": filename,
                "sids": subject_ids,
                "now": datetime.now(UTC),
            },
        )
        row = result.fetchone()
        best = row[0] if row else None

    await _set_cached(redis, cache_key, best if best else "none")
    return best


async def require_file_access(
    user: User,
    folder: FileFolder,
    filename: str,
    required: str,
    db: AsyncSession,
    redis: Redis,
) -> str:
    """Effective access to a file = max(folder ACL, file share).

    Returns the effective permission level or raises 403.
    """
    folder_perm = await resolve_folder_permission(user, folder, db, redis)
    share_perm = await resolve_file_share_permission(user, folder.id, filename, db, redis)

    candidates = [p for p in (folder_perm, share_perm) if p is not None]
    effective = max(candidates, key=lambda p: _PERM_RANK.get(p, 0)) if candidates else None
    if not perm_gte(effective, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient file permissions",
        )
    assert effective is not None
    return effective


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
    perms = await batch_resolve_folder_permissions(user, folders, db, redis)
    result = []
    for f in folders:
        perm = perms.get(f.id)
        if perm_gte(perm, min_perm):
            assert perm is not None
            result.append((f, perm))
    return result
