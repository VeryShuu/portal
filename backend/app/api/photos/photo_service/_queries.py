from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.photos import PhotoList, PhotoPublic
from app.services import photos_photo_repo as photo_repo

from .._common import _photo_to_public


async def list_folder_photos(
    db: AsyncSession,
    user: User,
    redis: Redis,
    folder_id: uuid.UUID,
    *,
    page: int,
    per_page: int,
    sort: str,
    min_date: datetime | None,
    max_date: datetime | None,
    min_size: int | None,
    max_size: int | None,
    mime_type: str | None,
    tag_id: uuid.UUID | None = None,
) -> PhotoList:
    from app.api.photos import photo_service as _ps

    folder = await photo_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    from app.core.constants import PERM_VIEWER

    await _ps.require_folder_permission(user, folder, PERM_VIEWER, db, redis)

    total = await photo_repo.count_folder_photos(
        db,
        folder_id,
        min_date=min_date,
        max_date=max_date,
        min_size=min_size,
        max_size=max_size,
        mime_type=mime_type,
        tag_id=tag_id,
    )
    rows = await photo_repo.fetch_folder_photos_page(
        db,
        folder_id,
        sort=sort,
        min_date=min_date,
        max_date=max_date,
        min_size=min_size,
        max_size=max_size,
        mime_type=mime_type,
        offset=(page - 1) * per_page,
        limit=per_page,
        tag_id=tag_id,
    )
    items = [_photo_to_public(p, folder) for p in rows]
    return PhotoList(items=items, total=total, page=page, per_page=per_page)


async def list_recent_photos(
    db: AsyncSession, user: User, redis: Redis, *, limit: int
) -> list[PhotoPublic]:
    from app.api.photos import photo_service as _ps

    cfg = _ps._module_settings()
    if not cfg.enabled:
        return []
    eff_limit = min(limit, cfg.widget_limit or 8)

    out: list[PhotoPublic] = []
    chunk_size = max(50, eff_limit * 2)
    offset = 0
    max_total_checks = 500

    while len(out) < eff_limit and offset < max_total_checks:
        rows = await photo_repo.fetch_recent_photos_with_folders(db, chunk_size, offset=offset)
        if not rows:
            break

        if user.role != "admin":
            unique_folders = {}
            for _photo, folder in rows:
                if folder.id not in unique_folders:
                    unique_folders[folder.id] = folder
            folder_list = list(unique_folders.values())
            folder_perms = await _ps.resolve_folders_permissions_batch(user, folder_list, db, redis)
        else:
            folder_perms = {}

        for photo, folder in rows:
            if user.role != "admin":
                perm = folder_perms.get(folder.id)
                if perm is None:
                    continue
            out.append(_photo_to_public(photo, folder))
            if len(out) >= eff_limit:
                break

        offset += chunk_size

    return out[:eff_limit]


async def get_storage_stats(db: AsyncSession) -> dict:
    return await photo_repo.fetch_storage_stats(db)
