"""Photo CRUD, bulk operations, upload, and storage stats."""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import delete, func, select

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_MANAGER, PERM_UPLOADER, PERM_VIEWER
from app.core.uploads import stream_upload_to_path
from app.models.photos import Photo, PhotoFolder, PhotoTagAssignment
from app.schemas.photos import (
    BulkActionRequest,
    BulkActionResponse,
    PhotoList,
    PhotoPublic,
    UpdatePhotoRequest,
    UploadResult,
    UploadResultItem,
)
from app.services import photos_storage
from app.services.audit import push_audit_event
from app.services.photos_acl import (
    perm_gte,
    require_folder_permission,
    require_photo_permission,
    resolve_folder_permission,
    resolve_photo_permission,
)

from ._common import (
    _enqueue_processing,
    _module_settings,
    _photo_to_public,
    logger,
)

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
) -> PhotoList:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_VIEWER, db, redis)

    sort_col = {
        "created_at": Photo.created_at,
        "taken_at": Photo.taken_at,
        "original_name": Photo.original_name,
    }[sort]
    base = select(Photo).where(Photo.folder_id == folder_id, Photo.deleted_at.is_(None))
    if min_date is not None:
        base = base.where(Photo.taken_at.isnot(None), Photo.taken_at >= min_date)
    if max_date is not None:
        base = base.where(Photo.taken_at.isnot(None), Photo.taken_at <= max_date)
    if min_size is not None:
        base = base.where(Photo.size_bytes >= min_size)
    if max_size is not None:
        base = base.where(Photo.size_bytes <= max_size)
    if mime_type is not None:
        base = base.where(Photo.mime_type == mime_type)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    res2 = await db.execute(
        base.order_by(sort_col.desc().nullslast() if sort != "original_name" else sort_col.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = [_photo_to_public(p, folder_path=folder.path) for p in res2.scalars().all()]
    return PhotoList(items=items, total=int(total or 0), page=page, per_page=per_page)


@router.get("/deleted", response_model=PhotoList)
async def list_deleted_photos(
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> PhotoList:
    cutoff = datetime.now(UTC) - timedelta(days=30)
    offset = (page - 1) * per_page

    if user.role == "admin":
        base_cond = [Photo.deleted_at.isnot(None), Photo.deleted_at > cutoff]
        count_q = select(func.count()).select_from(
            select(Photo)
            .join(PhotoFolder, Photo.folder_id == PhotoFolder.id, isouter=True)
            .where(*base_cond)
            .subquery()
        )
        total = (await db.scalar(count_q)) or 0
        stmt = (
            select(Photo, PhotoFolder)
            .join(PhotoFolder, Photo.folder_id == PhotoFolder.id, isouter=True)
            .where(*base_cond)
            .order_by(Photo.deleted_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        rows = (await db.execute(stmt)).all()
        items = [
            _photo_to_public(photo, folder_path=folder.path if folder else None)
            for photo, folder in rows
        ]
        return PhotoList(items=items, total=int(total), page=page, per_page=per_page)

    res = await db.execute(
        select(Photo)
        .where(Photo.deleted_at.isnot(None), Photo.deleted_at > cutoff)
        .order_by(Photo.deleted_at.desc())
        .limit(2000)
    )
    all_photos = res.scalars().all()
    accessible_items: list[PhotoPublic] = []
    for photo in all_photos:
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder is None:
            continue
        perm = await resolve_folder_permission(user, folder, db, redis)
        if not perm_gte(perm, PERM_MANAGER):
            continue
        accessible_items.append(
            _photo_to_public(photo, folder_path=folder.path if folder else None)
        )

    total = len(accessible_items)
    items = accessible_items[offset : offset + per_page]
    return PhotoList(items=items, total=total, page=page, per_page=per_page)


@router.get("/recent", response_model=list[PhotoPublic])
async def list_recent_photos(
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    limit: int = Query(8, ge=1, le=50),
) -> list[PhotoPublic]:
    cfg = _module_settings()
    if not cfg.enabled:
        return []
    eff_limit = min(limit, cfg.widget_limit or 8)
    res = await db.execute(
        select(Photo, PhotoFolder)
        .join(PhotoFolder, Photo.folder_id == PhotoFolder.id)
        .where(
            Photo.deleted_at.is_(None), PhotoFolder.deleted_at.is_(None), Photo.processed.is_(True)
        )
        .order_by(Photo.created_at.desc())
        .limit(eff_limit * 6)
    )
    rows = res.all()
    out: list[PhotoPublic] = []
    for photo, folder in rows:
        if user.role != "admin":
            perm = await resolve_folder_permission(user, folder, db, redis)
            if perm is None:
                continue
        out.append(_photo_to_public(photo, folder_path=folder.path))
        if len(out) >= eff_limit:
            break
    return out


@router.get("/storage-stats")
async def get_storage_stats(db: DbDep, user: AdminDep) -> dict:
    res = await db.execute(
        select(
            PhotoFolder.id,
            PhotoFolder.name,
            PhotoFolder.path,
            func.coalesce(func.sum(Photo.size_bytes), 0).label("size_bytes"),
            func.count(Photo.id).label("file_count"),
        )
        .join(Photo, Photo.folder_id == PhotoFolder.id)
        .where(Photo.deleted_at.is_(None), PhotoFolder.deleted_at.is_(None))
        .group_by(PhotoFolder.id, PhotoFolder.name, PhotoFolder.path)
        .order_by(func.sum(Photo.size_bytes).desc())
        .limit(50)
    )
    rows = res.all()
    top_folders = [
        {
            "folder_id": str(r[0]),
            "folder_name": r[1],
            "folder_path": r[2],
            "size_bytes": int(r[3]),
            "file_count": int(r[4]),
        }
        for r in rows
    ]
    total_size = sum(f["size_bytes"] for f in top_folders)
    total_files = sum(f["file_count"] for f in top_folders)
    return {"total_size_bytes": total_size, "total_files": total_files, "top_folders": top_folders}


@router.get("/{photo_id}", response_model=PhotoPublic)
async def get_photo(
    photo_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> PhotoPublic:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_VIEWER, db, redis)
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    return _photo_to_public(photo, folder_path=folder.path if folder else None)


@router.patch("/{photo_id}", response_model=PhotoPublic)
async def update_photo(
    photo_id: uuid.UUID, data: UpdatePhotoRequest, db: DbDep, user: CurrentUser, redis: RedisDep
) -> PhotoPublic:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_UPLOADER, db, redis)
    if data.description is not None:
        photo.description = data.description
    if data.folder_id is not None and data.folder_id != photo.folder_id:
        target = await db.scalar(
            select(PhotoFolder).where(
                PhotoFolder.id == data.folder_id, PhotoFolder.deleted_at.is_(None)
            )
        )
        if not target:
            raise HTTPException(status_code=404, detail="Target folder not found")
        await require_folder_permission(user, target, PERM_UPLOADER, db, redis)
        photo.folder_id = data.folder_id
    await db.commit()
    await db.refresh(photo)
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    return _photo_to_public(photo, folder_path=folder.path if folder else None)


@router.delete("/{photo_id}", status_code=204)
async def delete_photo(
    photo_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploaded_by != user.id and user.role != "admin":
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if not folder:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    photo.deleted_at = datetime.now(UTC)
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
    photo_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> PhotoPublic:
    res = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.deleted_at is None:
        raise HTTPException(status_code=400, detail="Photo is not deleted")
    if user.role != "admin" and photo.uploaded_by != user.id:
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder:
            await require_folder_permission(user, folder, PERM_UPLOADER, db, redis)
        else:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    photo.deleted_at = None
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
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    return _photo_to_public(photo, folder_path=folder.path if folder else None)


@router.delete("/{photo_id}/purge", status_code=204)
async def purge_photo(
    photo_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    """Окончательно удаляет фото из корзины (файлы + запись в БД)."""
    res = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.deleted_at is None:
        raise HTTPException(status_code=400, detail="Photo is not in trash")
    if user.role != "admin" and photo.uploaded_by != user.id:
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder:
            await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
        else:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    original: Path | None = None
    if folder:
        original = photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
    photos_storage.delete_photo_files(original, photo.id)
    await db.execute(delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == photo_id))
    await db.execute(delete(Photo).where(Photo.id == photo_id))
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


_TRASH_EMPTY_BATCH = 500


@router.post("/trash/empty", status_code=200)
async def empty_trash(request: Request, db: DbDep, user: AdminDep, redis: RedisDep) -> dict:
    """Окончательно удаляет ВСЕ фото из корзины (только admin). Батчевая обработка."""
    purged = 0
    while True:
        rows = (
            await db.execute(
                select(Photo, PhotoFolder)
                .join(PhotoFolder, Photo.folder_id == PhotoFolder.id, isouter=True)
                .where(Photo.deleted_at.isnot(None))
                .limit(_TRASH_EMPTY_BATCH)
            )
        ).all()
        if not rows:
            break
        photo_ids = [photo.id for photo, _ in rows]
        for photo, folder in rows:
            try:
                original: Path | None = None
                if folder:
                    original = (
                        photos_storage.folder_fs_path(folder.fs_path or folder.path)
                        / photo.filename
                    )
                photos_storage.delete_photo_files(original, photo.id)
                purged += 1
            except Exception as exc:
                logger.warning("photos.trash.empty_failed", photo_id=str(photo.id), error=str(exc))
        await db.execute(
            delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id.in_(photo_ids))
        )
        await db.execute(delete(Photo).where(Photo.id.in_(photo_ids)))
        await db.commit()
    await push_audit_event(
        redis,
        event_type="photos.trash_emptied",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo",
        resource_id="all",
        ip_address=request.client.host if request.client else None,
    )
    return {"purged": purged}


@router.post("/bulk", response_model=BulkActionResponse)
async def bulk_action(
    data: BulkActionRequest, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> BulkActionResponse:
    import shutil as _shutil

    processed = 0
    errors: list[str] = []

    target_folder: PhotoFolder | None = None
    if data.action == "move":
        if data.target_folder_id is None:
            raise HTTPException(status_code=400, detail="target_folder_id required for move")
        tf_res = await db.execute(
            select(PhotoFolder).where(
                PhotoFolder.id == data.target_folder_id, PhotoFolder.deleted_at.is_(None)
            )
        )
        target_folder = tf_res.scalar_one_or_none()
        if not target_folder:
            raise HTTPException(status_code=404, detail="Target folder not found")
        if user.role != "admin":
            await require_folder_permission(user, target_folder, PERM_UPLOADER, db, redis)

    moved_files: list[tuple[str, str]] = []

    for photo_id in data.photo_ids:
        try:
            ph_res = await db.execute(
                select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None))
            )
            photo = ph_res.scalar_one_or_none()
            if not photo:
                errors.append(f"{photo_id}: not found")
                continue

            src_folder_res = await db.execute(
                select(PhotoFolder).where(PhotoFolder.id == photo.folder_id)
            )
            src_folder = src_folder_res.scalar_one_or_none()

            if user.role != "admin":
                if src_folder:
                    src_perm = await resolve_folder_permission(user, src_folder, db, redis)
                else:
                    src_perm = None
                if not src_perm:
                    errors.append(f"{photo_id}: no access to source folder")
                    continue

            if data.action == "delete":
                if user.role != "admin":
                    perm = await resolve_photo_permission(user, photo, db, redis)
                    if not perm_gte(perm, PERM_UPLOADER):
                        errors.append(f"{photo_id}: insufficient permissions")
                        continue
                photo.deleted_at = datetime.now(UTC)
                processed += 1

            elif data.action == "move" and target_folder is not None:
                if user.role != "admin":
                    src_perm = await resolve_photo_permission(user, photo, db, redis)
                    if not perm_gte(src_perm, PERM_UPLOADER):
                        errors.append(f"{photo_id}: insufficient permissions in source folder")
                        continue

                if src_folder:
                    src_dir = photos_storage.folder_fs_path(src_folder.fs_path or src_folder.path)
                    dst_dir = photos_storage.folder_fs_path(
                        target_folder.fs_path or target_folder.path
                    )
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    src_file = src_dir / photo.filename
                    dst_file = dst_dir / photo.filename
                    if src_file.exists() and not dst_file.exists():
                        _shutil.move(str(src_file), str(dst_file))
                        moved_files.append((str(dst_file), str(src_file)))
                    elif src_file.exists() and dst_file.exists():
                        stem = Path(photo.filename).stem
                        ext = Path(photo.filename).suffix
                        candidate = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
                        new_dst = str(dst_dir / candidate)
                        _shutil.move(str(src_file), new_dst)
                        moved_files.append((new_dst, str(src_file)))
                        photo.filename = candidate

                photo.folder_id = data.target_folder_id  # type: ignore[assignment]
                processed += 1

        except Exception as exc:
            errors.append(f"{photo_id}: {exc}")

    try:
        await db.commit()
    except Exception:
        for dst, src in reversed(moved_files):
            try:
                _shutil.move(dst, src)
            except Exception as rollback_exc:
                logger.error(
                    "photos.bulk_action.rollback_failed",
                    src=str(src),
                    dst=str(dst),
                    error=str(rollback_exc),
                )
        await db.rollback()
        raise
    return BulkActionResponse(processed=processed, errors=errors)


@router.post(
    "/folders/{folder_id}/upload",
    response_model=UploadResult,
    dependencies=[Depends(RateLimiter(times=20, minutes=1))],
)
async def upload_photos(
    folder_id: uuid.UUID,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    files: list[UploadFile] = File(...),
) -> UploadResult:
    cfg = _module_settings()
    if not cfg.enabled:
        raise HTTPException(status_code=503, detail="Photos module disabled")

    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_UPLOADER, db, redis)

    max_bytes = (cfg.max_size_mb or 50) * 1024 * 1024
    allowed_mime = set(cfg.allowed_mime or [])
    items: list[UploadResultItem] = []

    for f in files:
        final_path: Path | None = None
        try:
            if not photos_storage.is_allowed_ext(f.filename or ""):
                items.append(
                    UploadResultItem(
                        original_name=f.filename or "?", ok=False, error="extension not allowed"
                    )
                )
                continue
            effective_ct = f.content_type or ""

            target_dir = photos_storage.folder_fs_path(folder.fs_path or folder.path)
            target_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = target_dir / f"_tmp_{uuid.uuid4().hex}"
            written, detected_mime = await stream_upload_to_path(
                f,
                tmp_path,
                max_size=max_bytes,
                allowed_mimes=allowed_mime,
            )
            safe = photos_storage.sanitize_filename(f.filename or "photo.bin")
            stem, ext = Path(safe).stem, (Path(safe).suffix.lower() or ".bin")
            fname = safe
            idx = 1
            while (target_dir / fname).exists():
                fname = f"{stem}-{idx}{ext}"
                idx += 1
                if idx > 9999:
                    fname = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
                    break
            final_path = target_dir / fname
            tmp_path.rename(final_path)
            size = written

            try:
                photo = Photo(
                    folder_id=folder_id,
                    filename=fname,
                    original_name=f.filename or fname,
                    size_bytes=size,
                    mime_type=detected_mime or effective_ct or None,
                    uploaded_by=user.id,
                )
                db.add(photo)
                await db.commit()
                await db.refresh(photo)
            except Exception:
                with contextlib.suppress(Exception):
                    final_path.unlink(missing_ok=True)
                raise
            await _enqueue_processing(request, photo.id)
            await push_audit_event(
                redis,
                event_type="photos.photo_uploaded",
                user_id=str(user.id),
                user_email=user.email,
                resource_type="photo",
                resource_id=str(photo.id),
                resource_title=photo.original_name,
                metadata={"folder_id": str(folder_id), "size_bytes": size},
            )
            items.append(
                UploadResultItem(photo_id=photo.id, original_name=photo.original_name, ok=True)
            )
        except Exception as exc:
            logger.exception("photos.upload_failed", filename=f.filename, error=str(exc))
            items.append(
                UploadResultItem(original_name=f.filename or "?", ok=False, error=str(exc))
            )

    return UploadResult(items=items)
