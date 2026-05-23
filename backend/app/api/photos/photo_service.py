from __future__ import annotations

import contextlib
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PERM_MANAGER, PERM_UPLOADER
from app.core.uploads import stream_upload_to_path
from app.models.photos import Photo, PhotoFolder
from app.models.user import User
from app.schemas.photos import (
    BulkActionRequest,
    BulkActionResponse,
    PhotoList,
    PhotoPublic,
    UploadResult,
    UploadResultItem,
)
from app.services import photos_storage
from app.services.audit import push_audit_event
from app.services.photos_acl import (
    perm_gte,
    require_folder_permission,
    resolve_folder_permission,
    resolve_photo_permission,
    resolve_folders_permissions_batch,
)

from . import photo_repo
from ._common import _enqueue_processing, _module_settings, _photo_to_public, logger


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
    folder = await photo_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    from app.core.constants import PERM_VIEWER

    await require_folder_permission(user, folder, PERM_VIEWER, db, redis)

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
    items = [_photo_to_public(p, folder_path=folder.path) for p in rows]
    return PhotoList(items=items, total=total, page=page, per_page=per_page)





async def list_recent_photos(
    db: AsyncSession, user: User, redis: Redis, *, limit: int
) -> list[PhotoPublic]:
    cfg = _module_settings()
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
            folder_perms = await resolve_folders_permissions_batch(user, folder_list, db, redis)
        else:
            folder_perms = {}

        for photo, folder in rows:
            if user.role != "admin":
                perm = folder_perms.get(folder.id)
                if perm is None:
                    continue
            out.append(_photo_to_public(photo, folder_path=folder.path))
            if len(out) >= eff_limit:
                break

        offset += chunk_size

    return out[:eff_limit]


async def get_storage_stats(db: AsyncSession) -> dict:
    rows = await photo_repo.fetch_storage_stats_top_folders(db)
    top_folders: list[dict] = [
        {
            "folder_id": str(r[0]),
            "folder_name": r[1],
            "folder_path": r[2],
            "size_bytes": int(r[3]),
            "file_count": int(r[4]),
        }
        for r in rows
    ]
    total_size, total_files = await photo_repo.fetch_global_storage_totals(db)
    return {
        "total_size_bytes": total_size,
        "total_files": total_files,
        "top_folders": top_folders,
    }





async def _load_bulk_target_folder(
    db: AsyncSession,
    user: User,
    redis: Redis,
    target_folder_id: uuid.UUID | None,
) -> PhotoFolder:
    if target_folder_id is None:
        raise HTTPException(status_code=400, detail="target_folder_id required for move")
    target_folder = await photo_repo.fetch_active_folder(db, target_folder_id)
    if not target_folder:
        raise HTTPException(status_code=404, detail="Target folder not found")
    if user.role != "admin":
        await require_folder_permission(user, target_folder, PERM_UPLOADER, db, redis)
    return target_folder


async def _bulk_delete_photo(
    photo: Photo, user: User, db: AsyncSession, redis: Redis
) -> str | None:
    from app.api.photos.trash_service import TrashService

    if user.role != "admin":
        perm = await resolve_photo_permission(user, photo, db, redis)
        if not perm_gte(perm, PERM_UPLOADER):
            return "insufficient permissions"
    TrashService.mark_photo_deleted(photo)
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
    if user.role != "admin":
        src_perm = await resolve_photo_permission(user, photo, db, redis)
        if not perm_gte(src_perm, PERM_UPLOADER):
            return "insufficient permissions in source folder"

    if src_folder:
        src_dir = photos_storage.folder_fs_path(src_folder.fs_path or src_folder.path)
        dst_dir = photos_storage.folder_fs_path(target_folder.fs_path or target_folder.path)
        dst_dir.mkdir(parents=True, exist_ok=True)
        src_file = src_dir / photo.filename
        dst_file = dst_dir / photo.filename
        if src_file.exists() and not dst_file.exists():
            shutil.move(str(src_file), str(dst_file))
            moved_files.append((str(dst_file), str(src_file)))
        elif src_file.exists() and dst_file.exists():
            stem = Path(photo.filename).stem
            ext = Path(photo.filename).suffix
            candidate = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
            new_dst = str(dst_dir / candidate)
            shutil.move(str(src_file), new_dst)
            moved_files.append((new_dst, str(src_file)))
            photo.filename = candidate

    photo.folder_id = target_folder_id
    return None


async def _commit_bulk_or_revert_files(
    db: AsyncSession, moved_files: list[tuple[str, str]]
) -> None:
    try:
        await db.commit()
    except Exception:
        for dst, src in reversed(moved_files):
            try:
                shutil.move(dst, src)
            except Exception as rollback_exc:
                logger.error(
                    "photos.bulk_action.rollback_failed",
                    src=str(src),
                    dst=str(dst),
                    error=str(rollback_exc),
                )
        await db.rollback()
        raise


async def perform_bulk_action(
    db: AsyncSession,
    user: User,
    redis: Redis,
    data: BulkActionRequest,
) -> BulkActionResponse:
    processed = 0
    errors: list[str] = []

    target_folder: PhotoFolder | None = None
    if data.action == "move":
        target_folder = await _load_bulk_target_folder(db, user, redis, data.target_folder_id)

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
                    await resolve_folder_permission(user, src_folder, db, redis)
                    if src_folder
                    else None
                )
                if not src_perm:
                    errors.append(f"{photo_id}: no access to source folder")
                    continue

            if data.action == "delete":
                err = await _bulk_delete_photo(photo, user, db, redis)
            elif data.action == "move" and target_folder is not None:
                err = await _bulk_move_photo(
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

    await _commit_bulk_or_revert_files(db, moved_files)
    return BulkActionResponse(processed=processed, errors=errors)


async def _save_single_upload(
    f: UploadFile,
    folder: PhotoFolder,
    folder_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    *,
    max_bytes: int,
    allowed_mime: set[str],
) -> tuple[Photo | None, int, Path | None, UploadResultItem | None]:
    final_path: Path | None = None
    try:
        if not photos_storage.is_allowed_ext(f.filename or ""):
            return (
                None,
                0,
                None,
                UploadResultItem(
                    original_name=f.filename or "?", ok=False, error="extension not allowed"
                ),
            )
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

        async with db.begin_nested():
            photo = Photo(
                folder_id=folder_id,
                filename=fname,
                original_name=f.filename or fname,
                size_bytes=size,
                mime_type=detected_mime or effective_ct or None,
                uploaded_by=user.id,
            )
            db.add(photo)
            await db.flush()
        return photo, size, final_path, None
    except Exception as exc:
        if final_path is not None:
            with contextlib.suppress(Exception):
                final_path.unlink(missing_ok=True)
        logger.exception("photos.upload_failed", filename=f.filename, error=str(exc))
        return (
            None,
            0,
            None,
            UploadResultItem(original_name=f.filename or "?", ok=False, error=str(exc)),
        )


async def perform_upload(
    db: AsyncSession,
    user: User,
    redis: Redis,
    request: Request,
    folder_id: uuid.UUID,
    files: list[UploadFile],
) -> UploadResult:
    cfg = _module_settings()
    if not cfg.enabled:
        raise HTTPException(status_code=503, detail="Photos module disabled")

    folder = await photo_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_UPLOADER, db, redis)

    max_bytes = (cfg.max_size_mb or 50) * 1024 * 1024
    allowed_mime = set(cfg.allowed_mime or [])
    items: list[UploadResultItem] = []
    pending: list[tuple[Photo, int, Path]] = []

    for f in files:
        try:
            async with db.begin_nested():
                photo, size, final_path, err_item = await _save_single_upload(
                    f, folder, folder_id, user, db, max_bytes=max_bytes, allowed_mime=allowed_mime
                )
                if err_item is not None:
                    items.append(err_item)
                    raise ValueError(err_item.error or "Upload failed")
                elif photo is not None and final_path is not None:
                    pending.append((photo, size, final_path))
        except Exception as exc:
            logger.warning("photos.upload.file_failed", filename=f.filename, error=str(exc))
            if not any(item.original_name == (f.filename or "?") for item in items):
                items.append(
                    UploadResultItem(
                        original_name=f.filename or "?",
                        ok=False,
                        error=str(exc),
                    )
                )

    if pending:
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            for _, _, path in pending:
                with contextlib.suppress(Exception):
                    path.unlink(missing_ok=True)
            logger.exception("photos.upload_commit_failed", error=str(exc))
            for photo, _, _ in pending:
                items.append(
                    UploadResultItem(
                        original_name=photo.original_name,
                        ok=False,
                        error="database error",
                    )
                )
            return UploadResult(items=items)

        for photo, size, _ in pending:
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

    return UploadResult(items=items)
