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


def _cache_key(user_id: uuid.UUID, folder_id: uuid.UUID) -> str:
    return f"photos_acl:{user_id}:folder:{folder_id}"


async def invalidate_folder_cache(
    redis: Redis, folder_id: uuid.UUID, db: AsyncSession | None = None
) -> None:
    try:
        await _scan_and_delete(redis, f"photos_acl:*:folder:{folder_id}")
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
                await _scan_and_delete(redis, f"photos_acl:*:folder:{child_id}")
    except Exception:
        pass


async def invalidate_user_cache(redis: Redis, user_id: uuid.UUID) -> None:
    with contextlib.suppress(Exception):
        await _scan_and_delete(redis, f"photos_acl:{user_id}:folder:*")


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
                FROM photo_folders f JOIN ancestors a ON f.parent_id = a.id
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

    cache_key = _cache_key(user.id, folder.id)
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


async def filter_accessible_folders(
    user: User,
    folders: list[PhotoFolder],
    db: AsyncSession,
    redis: Redis,
) -> list[PhotoFolder]:
    if user.role == "admin":
        return folders
    accessible = []
    for f in folders:
        perm = await resolve_folder_permission(user, f, db, redis)
        if perm is not None:
            accessible.append(f)
    return accessible
