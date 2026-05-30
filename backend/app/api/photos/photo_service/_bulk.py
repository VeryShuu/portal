from __future__ import annotations

import uuid

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PERM_UPLOADER
from app.models.photos import Photo, PhotoFolder
from app.models.user import User
from app.schemas.photos import BulkActionRequest, BulkActionResponse
from app.services import photos_photo_repo as photo_repo


async def _load_bulk_target_folder(
    db: AsyncSession,
    user: User,
    redis: Redis,
    target_folder_id: uuid.UUID | None,
) -> PhotoFolder:
    from app.api.photos import photo_service as _ps

    if target_folder_id is None:
        raise HTTPException(status_code=400, detail="target_folder_id required for move")
    target_folder = await photo_repo.fetch_active_folder(db, target_folder_id)
    if not target_folder:
        raise HTTPException(status_code=404, detail="Target folder not found")
    if user.role != "admin":
        await _ps.require_folder_permission(user, target_folder, PERM_UPLOADER, db, redis)
    return target_folder


async def _bulk_delete_photo(
    photo: Photo, user: User, db: AsyncSession, redis: Redis
) -> str | None:
    from app.api.photos import photo_service as _ps

    if user.role != "admin":
        perm = await _ps.resolve_photo_permission(user, photo, db, redis)
        if not _ps.perm_gte(perm, PERM_UPLOADER):
            return "insufficient permissions"
    _ps.TrashService.mark_photo_deleted(photo)
    return None


async def _bulk_move_photo(
    photo: Photo,
    src_folder: PhotoFolder | None,
    target_folder: PhotoFolder,
    target_folder_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    redis: Redis,
    moved_files: list[tuple[str, str]],
) -> str | None:
    from app.api.photos import photo_service as _ps

    if user.role != "admin":
        src_perm = await _ps.resolve_photo_permission(user, photo, db, redis)
        if not _ps.perm_gte(src_perm, PERM_UPLOADER):
            return "insufficient permissions in source folder"

    _ps._move_photo_file_on_disk(photo, src_folder, target_folder, moved_files)
    photo.folder_id = target_folder_id
    return None


async def perform_bulk_action(
    db: AsyncSession,
    user: User,
    redis: Redis,
    data: BulkActionRequest,
) -> BulkActionResponse:
    from app.api.photos import photo_service as _ps

    processed = 0
    errors: list[str] = []

    target_folder: PhotoFolder | None = None
    if data.action == "move":
        target_folder = await _ps._load_bulk_target_folder(db, user, redis, data.target_folder_id)

    photos_by_id = await photo_repo.fetch_active_photos_map(db, data.photo_ids)
    unique_folder_ids = {p.folder_id for p in photos_by_id.values() if p.folder_id is not None}
    folders_by_id = await photo_repo.fetch_folders_map(db, unique_folder_ids)
    moved_files: list[tuple[str, str]] = []

    for photo_id in data.photo_ids:
        try:
            photo = photos_by_id.get(photo_id)
            if not photo:
                errors.append(f"{photo_id}: not found")
                continue

            src_folder = folders_by_id.get(photo.folder_id) if photo.folder_id else None

            if user.role != "admin":
                src_perm = (
                    await _ps.resolve_folder_permission(user, src_folder, db, redis)
                    if src_folder
                    else None
                )
                if not src_perm:
                    errors.append(f"{photo_id}: no access to source folder")
                    continue

            if data.action == "delete":
                err = await _ps._bulk_delete_photo(photo, user, db, redis)
            elif data.action == "move" and target_folder is not None:
                err = await _ps._bulk_move_photo(
                    photo,
                    src_folder,
                    target_folder,
                    data.target_folder_id,  # type: ignore[arg-type]
                    user,
                    db,
                    redis,
                    moved_files,
                )
            else:
                err = None

            if err is not None:
                errors.append(f"{photo_id}: {err}")
            else:
                processed += 1

        except Exception as exc:
            errors.append(f"{photo_id}: {exc}")

    await _ps._commit_bulk_or_revert_files(db, moved_files)
    return BulkActionResponse(processed=processed, errors=errors)
