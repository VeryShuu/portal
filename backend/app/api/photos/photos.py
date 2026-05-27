"""Photo endpoints: thin HTTP layer over ``photo_service`` / ``photo_repo``."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from fastapi_limiter.depends import RateLimiter

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_MANAGER, PERM_UPLOADER, PERM_VIEWER
from app.schemas.photos import (
    BulkActionRequest,
    BulkActionResponse,
    PhotoList,
    PhotoPublic,
    UpdatePhotoRequest,
    UploadResult,
)
from app.services import photos_photo_repo as photo_repo
from app.services.audit import push_audit_event
from app.services.photos_acl import (
    require_folder_permission,
    require_photo_permission,
)
from app.services.photos_trash import TrashService

from . import photo_service
from ._common import _photo_to_public

router = APIRouter()


@router.get("/folders/{folder_id}/photos", response_model=PhotoList)
async def list_folder_photos(
    folder_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = Query("created_at", pattern=r"^(created_at|taken_at|original_name)$"),
    min_date: datetime | None = Query(default=None),
    max_date: datetime | None = Query(default=None),
    min_size: int | None = Query(default=None, ge=0),
    max_size: int | None = Query(default=None, ge=0),
    mime_type: str | None = Query(default=None),
    tag_id: uuid.UUID | None = Query(default=None),
) -> PhotoList:
    return await photo_service.list_folder_photos(
        db,
        user,
        redis,
        folder_id,
        page=page,
        per_page=per_page,
        sort=sort,
        min_date=min_date,
        max_date=max_date,
        min_size=min_size,
        max_size=max_size,
        mime_type=mime_type,
        tag_id=tag_id,
    )


@router.get("/deleted", response_model=PhotoList)
async def list_deleted_photos(
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> PhotoList:
    return await TrashService.list_trashed_photos(db, user, redis, page=page, per_page=per_page)


@router.get("/recent", response_model=list[PhotoPublic])
async def list_recent_photos(
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    limit: int = Query(8, ge=1, le=50),
) -> list[PhotoPublic]:
    return await photo_service.list_recent_photos(db, user, redis, limit=limit)


@router.get("/storage-stats")
async def get_storage_stats(db: DbDep, user: AdminDep) -> dict:
    return await photo_service.get_storage_stats(db)


@router.get("/{photo_id}", response_model=PhotoPublic)
async def get_photo(
    photo_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> PhotoPublic:
    photo = await photo_repo.fetch_active_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_VIEWER, db, redis)
    folder = await photo_repo.fetch_folder(db, photo.folder_id)
    return _photo_to_public(photo, folder)


@router.patch("/{photo_id}", response_model=PhotoPublic)
async def update_photo(
    photo_id: uuid.UUID,
    data: UpdatePhotoRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PhotoPublic:
    photo = await photo_repo.fetch_active_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_UPLOADER, db, redis)
    if data.description is not None:
        photo.description = data.description
    if data.folder_id is not None and data.folder_id != photo.folder_id:
        target = await photo_repo.fetch_active_folder(db, data.folder_id)
        if not target:
            raise HTTPException(status_code=404, detail="Target folder not found")
        await require_folder_permission(user, target, PERM_UPLOADER, db, redis)
        await photo_service.move_photo_to_folder(db, photo, target)
    else:
        await db.commit()
    await db.refresh(photo)
    folder = await photo_repo.fetch_folder(db, photo.folder_id)
    return _photo_to_public(photo, folder)


@router.delete("/{photo_id}", status_code=204)
async def delete_photo(
    photo_id: uuid.UUID,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:

    photo = await photo_repo.fetch_active_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploaded_by != user.id and user.role != "admin":
        folder = await photo_repo.fetch_folder(db, photo.folder_id)
        if not folder:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    await TrashService.soft_delete_photo(db, photo_id)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="photos.photo_deleted",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo",
        resource_id=str(photo_id),
    )
    return Response(status_code=204)


@router.post("/{photo_id}/restore", response_model=PhotoPublic)
async def restore_photo(
    photo_id: uuid.UUID,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PhotoPublic:

    photo = await photo_repo.fetch_photo_any(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.deleted_at is None:
        raise HTTPException(status_code=400, detail="Photo is not deleted")
    if user.role != "admin" and photo.uploaded_by != user.id:
        folder = await photo_repo.fetch_folder(db, photo.folder_id)
        if folder:
            await require_folder_permission(user, folder, PERM_UPLOADER, db, redis)
        else:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    await TrashService.restore_photo(db, photo_id)
    await db.commit()
    await db.refresh(photo)
    await push_audit_event(
        redis,
        event_type="photos.photo_restored",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo",
        resource_id=str(photo_id),
    )
    folder = await photo_repo.fetch_folder(db, photo.folder_id)
    return _photo_to_public(photo, folder)


@router.delete("/{photo_id}/purge", status_code=204)
async def purge_photo(
    photo_id: uuid.UUID,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    """Окончательно удаляет фото из корзины (файлы + запись в БД)."""

    photo = await photo_repo.fetch_photo_any(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.deleted_at is None:
        raise HTTPException(status_code=400, detail="Photo is not in trash")
    if user.role != "admin" and photo.uploaded_by != user.id:
        folder = await photo_repo.fetch_folder(db, photo.folder_id)
        if folder:
            await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
        else:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    await TrashService.purge_photo(db, photo_id)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="photos.photo_purged",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo",
        resource_id=str(photo_id),
        ip_address=request.client.host if request.client else None,
    )
    return Response(status_code=204)


@router.post("/trash/empty", status_code=202)
async def empty_trash(
    request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> dict:
    """Очищает корзину фотогалереи.

    - Для admin: ставит фоновую ARQ-задачу, вычищающую ВСЮ корзину.
      Аудит-событие ``photos.trash_emptied`` публикуется самой задачей по завершении.
    - Для остальных пользователей: синхронно вычищает только те фото и папки,
      на которые у пользователя есть право ``manager``. Аудит-событие
      ``photos.trash_emptied`` публикуется немедленно.
    """
    if user.role == "admin":
        arq_pool = getattr(request.app.state, "arq_pool", None)
        if arq_pool is None:
            raise HTTPException(status_code=503, detail="Worker not available")

        job = await arq_pool.enqueue_job(
            "empty_photo_trash",
            str(user.id),
            _job_id="photos:empty_trash",
        )
        if job is None:
            return {"status": "already_queued_or_running"}

        await push_audit_event(
            redis,
            event_type="photos.trash_empty_requested",
            user_id=str(user.id),
            user_email=user.email,
            resource_type="photo",
            resource_id="all",
            ip_address=request.client.host if request.client else None,
        )
        return {"status": "queued"}

    # Не-admin: вычищаем только доступные пользователю (manager) элементы.

    await push_audit_event(
        redis,
        event_type="photos.trash_empty_requested",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo",
        resource_id="own",
        ip_address=request.client.host if request.client else None,
    )

    stats = await TrashService.empty_trash_for_user(db, user, redis)

    await push_audit_event(
        redis,
        event_type="photos.trash_emptied",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo",
        resource_id="own",
        ip_address=request.client.host if request.client else None,
        metadata={
            "purged": stats["purged_photos"],
            "folders_purged": stats["purged_folders"],
            "scope": "user",
        },
    )
    return {"status": "done", **stats}


@router.post("/bulk", response_model=BulkActionResponse)
async def bulk_action(
    data: BulkActionRequest,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> BulkActionResponse:
    return await photo_service.perform_bulk_action(db, user, redis, data)


@router.post(
    "/folders/{folder_id}/upload",
    response_model=UploadResult,
    dependencies=[Depends(RateLimiter(times=60, minutes=1))],
)
async def upload_photos(
    folder_id: uuid.UUID,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    files: list[UploadFile] = File(...),
) -> UploadResult:
    return await photo_service.perform_upload(db, user, redis, request, folder_id, files)
