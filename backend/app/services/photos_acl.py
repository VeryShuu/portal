"""ACL для модуля фотогалереи (ADR-030/031).

Алгоритм для папки:
  1. portal admin          → 'manager'
  2. created_by = user     → 'manager'
  3. photo_folder_permissions (этот уровень)
  4. рекурсия вверх по parent_id
  5. None → нет доступа → 403

Алгоритм для фото:
  1. portal admin          → 'manager'
  2. uploaded_by = user    → 'manager'
  3. inherit_permissions=False + локальный ACL на фото (на будущее; пока его нет, проваливаемся в 4)
  4. resolve_folder_permission(photo.folder)

Уровни: viewer < uploader < manager
"""

from __future__ import annotations

import contextlib
import uuid

from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PERM_MANAGER, PERM_UPLOADER, PERM_VIEWER
from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder
from app.models.user import User
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

logger = get_logger(__name__)

_PERM_RANK = {PERM_VIEWER: 1, PERM_UPLOADER: 2, PERM_MANAGER: 3}


def perm_gte(actual: str | None, required: str) -> bool:
    if actual is None:
        return False
    return _PERM_RANK.get(actual, 0) >= _PERM_RANK.get(required, 99)


def _cache_key(user_id: uuid.UUID, folder_id: uuid.UUID, version: str) -> str:
    return f"photo_acl:{user_id}:{folder_id}:v{version}"


async def invalidate_folder_cache(
    redis: Redis, folder_id: uuid.UUID, db: AsyncSession | None = None
) -> None:
    try:
        await redis.incr(f"photo_acl_ver:{folder_id}")
        if db is not None:
            result = await db.execute(
                text(
                    """
                    WITH RECURSIVE descendants AS (
                        SELECT id FROM photo_folders WHERE id = :folder_id
                        UNION ALL
                        SELECT f.id FROM photo_folders f
                        JOIN descendants d ON f.parent_id = d.id
                        WHERE f.deleted_at IS NULL
                    )
                    SELECT id FROM descendants WHERE id != :folder_id
                    """
                ),
                {"folder_id": folder_id},
            )
            for (child_id,) in result.fetchall():
                await redis.incr(f"photo_acl_ver:{child_id}")
    except Exception as e:
        logger.warning("photos.acl.invalidate_failed", error=str(e))


async def invalidate_user_cache(redis: Redis, user_id: uuid.UUID) -> None:
    with contextlib.suppress(Exception):
        await _scan_and_delete(redis, f"photo_acl:{user_id}:*")


async def _resolve_folder_via_cte(
    db: AsyncSession, folder_id: uuid.UUID, subject_ids: list[str]
) -> str | None:
    """Один рекурсивный CTE-запрос: все предки + их права за один SELECT."""
    if not subject_ids:
        return None
    result = await db.execute(
        text("""
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, 0 AS depth
                FROM photo_folders WHERE id = :folder_id
                UNION ALL
                SELECT f.id, f.parent_id, a.depth + 1
                FROM photo_folders f JOIN ancestors a ON f.id = a.parent_id
                WHERE a.depth < 20
            )
            SELECT p.permission
            FROM ancestors a
            JOIN photo_folder_permissions p ON p.folder_id = a.id
            WHERE p.subject_id = ANY(:sids)
            ORDER BY CASE p.permission
                WHEN 'manager'  THEN 3
                WHEN 'uploader' THEN 2
                WHEN 'viewer'   THEN 1
                ELSE 0 END DESC
            LIMIT 1
        """),
        {"folder_id": str(folder_id), "sids": subject_ids},
    )
    row = result.fetchone()
    return row[0] if row else None


async def resolve_folder_permission(
    user: User,
    folder: PhotoFolder,
    db: AsyncSession,
    redis: Redis,
) -> str | None:
    """Возвращает лучшее право пользователя на папку (с рекурсией вверх).

    Returns: 'viewer' | 'uploader' | 'manager' | None
    """
    if user.role == "admin":
        return PERM_MANAGER
    if folder.created_by == user.id:
        return PERM_MANAGER

    version = "0"
    if redis is not None:
        try:
            val = await redis.get(f"photo_acl_ver:{folder.id}")
            if val is not None:
                version = val.decode("utf-8") if isinstance(val, bytes) else str(val)
        except Exception as exc:
            logger.debug("photos_acl.folder_version_read_failed", error=str(exc))

    cache_key = _cache_key(user.id, folder.id, version)
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached if cached != "none" else None

    subject_ids = await _subject_ids_for_user(user)
    best = await _resolve_folder_via_cte(db, folder.id, subject_ids)

    await _set_cached(redis, cache_key, best if best else "none")
    return best


async def resolve_photo_permission(
    user: User,
    photo: Photo,
    db: AsyncSession,
    redis: Redis,
) -> str | None:
    if user.role == "admin":
        return PERM_MANAGER
    if photo.uploaded_by == user.id:
        return PERM_MANAGER

    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    folder = res.scalar_one_or_none()
    if not folder:
        return None
    return await resolve_folder_permission(user, folder, db, redis)


async def require_folder_permission(
    user: User,
    folder: PhotoFolder,
    required: str,
    db: AsyncSession,
    redis: Redis,
) -> None:
    from fastapi import HTTPException, status

    perm = await resolve_folder_permission(user, folder, db, redis)
    if not perm_gte(perm, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient photos permissions",
        )


async def require_photo_permission(
    user: User,
    photo: Photo,
    required: str,
    db: AsyncSession,
    redis: Redis,
) -> None:
    from fastapi import HTTPException, status

    perm = await resolve_photo_permission(user, photo, db, redis)
    if not perm_gte(perm, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient photos permissions",
        )


def _partition_owned_folders(
    user: User, folders: list[PhotoFolder]
) -> tuple[dict[uuid.UUID, str | None], list[PhotoFolder]]:
    """Folders created by the user resolve to 'manager' without a lookup."""
    owned: dict[uuid.UUID, str | None] = {}
    missing: list[PhotoFolder] = []
    for f in folders:
        if f.created_by == user.id:
            owned[f.id] = PERM_MANAGER
        else:
            missing.append(f)
    return owned, missing


async def _fetch_folder_versions(redis: Redis, folders: list[PhotoFolder]) -> dict[uuid.UUID, str]:
    versions: dict[uuid.UUID, str] = {}
    if redis is not None:
        try:
            version_keys = [f"photo_acl_ver:{f.id}" for f in folders]
            versions_raw = await redis.mget(*version_keys)
            for f, v_raw in zip(folders, versions_raw, strict=False):
                if v_raw is not None:
                    versions[f.id] = (
                        v_raw.decode("utf-8") if isinstance(v_raw, bytes) else str(v_raw)
                    )
                else:
                    versions[f.id] = "0"
            return versions
        except Exception:
            pass
    return {f.id: "0" for f in folders}


async def _read_cached_folder_perms(
    redis: Redis,
    user_id: uuid.UUID,
    folders: list[PhotoFolder],
    folder_versions: dict[uuid.UUID, str],
) -> tuple[dict[uuid.UUID, str | None], list[PhotoFolder]]:
    cache_keys = [_cache_key(user_id, f.id, folder_versions[f.id]) for f in folders]
    if redis is not None:
        try:
            cached_vals = await redis.mget(*cache_keys)
        except Exception:
            cached_vals = [None] * len(cache_keys)
    else:
        cached_vals = [None] * len(cache_keys)

    resolved: dict[uuid.UUID, str | None] = {}
    still_missing: list[PhotoFolder] = []
    for f, val in zip(folders, cached_vals, strict=False):
        if val is not None:
            decoded = val.decode("utf-8") if isinstance(val, bytes) else val
            resolved[f.id] = decoded if decoded != "none" else None
        else:
            still_missing.append(f)
    return resolved, still_missing


async def _cache_folder_perms(redis: Redis, mapping: dict[str, str]) -> None:
    if redis is None or not mapping:
        return
    try:
        await redis.mset(mapping)
        for key in mapping:
            await redis.expire(key, 3600)
    except Exception as exc:
        logger.debug("photos_acl.folder_perms_cache_write_failed", error=str(exc))


async def _resolve_folder_perms_via_db(
    db: AsyncSession, folder_ids: list[str], subject_ids: list[str]
) -> dict[uuid.UUID, str]:
    """One recursive CTE: best ancestor permission per target folder."""
    db_res = await db.execute(
        text("""
            WITH RECURSIVE ancestors AS (
                SELECT id AS folder_id, parent_id, id AS target_folder_id, 0 AS depth
                FROM photo_folders WHERE id = ANY(:folder_ids) AND deleted_at IS NULL
                UNION ALL
                SELECT f.id, f.parent_id, a.target_folder_id, a.depth + 1
                FROM photo_folders f JOIN ancestors a ON f.id = a.parent_id
                WHERE a.depth < 20 AND f.deleted_at IS NULL
            )
            SELECT a.target_folder_id, p.permission
            FROM ancestors a
            JOIN photo_folder_permissions p ON p.folder_id = a.folder_id
            WHERE p.subject_id = ANY(:sids)
        """),
        {"folder_ids": folder_ids, "sids": subject_ids},
    )

    best_perms: dict[uuid.UUID, str] = {}
    for row in db_res.fetchall():
        target_id = uuid.UUID(str(row[0])) if not isinstance(row[0], uuid.UUID) else row[0]
        perm = row[1]
        old_perm = best_perms.get(target_id)
        if old_perm is None or _PERM_RANK.get(perm, 0) > _PERM_RANK.get(old_perm, 0):
            best_perms[target_id] = perm
    return best_perms


async def resolve_folders_permissions_batch(
    user: User,
    folders: list[PhotoFolder],
    db: AsyncSession,
    redis: Redis,
) -> dict[uuid.UUID, str | None]:
    if user.role == "admin":
        return {f.id: PERM_MANAGER for f in folders}

    result_perms, missing_folders = _partition_owned_folders(user, folders)
    if not missing_folders:
        return result_perms

    folder_versions = await _fetch_folder_versions(redis, missing_folders)
    cached, still_missing = await _read_cached_folder_perms(
        redis, user.id, missing_folders, folder_versions
    )
    result_perms.update(cached)
    if not still_missing:
        return result_perms

    subject_ids = await _subject_ids_for_user(user)
    if not subject_ids:
        for f in still_missing:
            result_perms[f.id] = None
        await _cache_folder_perms(
            redis,
            {_cache_key(user.id, f.id, folder_versions[f.id]): "none" for f in still_missing},
        )
        return result_perms

    best_perms = await _resolve_folder_perms_via_db(
        db, [str(f.id) for f in still_missing], subject_ids
    )

    cache_mset: dict[str, str] = {}
    for f in still_missing:
        best = best_perms.get(f.id)
        result_perms[f.id] = best
        cache_mset[_cache_key(user.id, f.id, folder_versions[f.id])] = best if best else "none"

    await _cache_folder_perms(redis, cache_mset)
    return result_perms


async def filter_accessible_folders(
    user: User,
    folders: list[PhotoFolder],
    db: AsyncSession,
    redis: Redis,
) -> list[PhotoFolder]:
    if user.role == "admin":
        return folders
    perms = await resolve_folders_permissions_batch(user, folders, db, redis)
    return [f for f in folders if perms.get(f.id) is not None]


async def filter_accessible_folders_with_perm(
    user: User,
    folders: list[PhotoFolder],
    db: AsyncSession,
    redis: Redis,
) -> list[tuple[PhotoFolder, str]]:
    if user.role == "admin":
        return [(f, PERM_MANAGER) for f in folders]
    perms = await resolve_folders_permissions_batch(user, folders, db, redis)
    result: list[tuple[PhotoFolder, str]] = []
    for f in folders:
        perm = perms.get(f.id)
        if perm is not None:
            result.append((f, perm))
    return result
