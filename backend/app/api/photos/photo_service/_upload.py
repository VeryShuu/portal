from __future__ import annotations

import contextlib
import uuid
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PERM_UPLOADER
from app.core.uploads import stream_upload_to_path
from app.models.photos import Photo, PhotoFolder
from app.models.user import User
from app.schemas.photos import UploadResult, UploadResultItem
from app.services import photos_photo_repo as photo_repo
from app.services import photos_storage

from .._common import logger


def _pick_unique_filename(target_dir: Path, raw_name: str | None) -> str:
    """Подбирает уникальное безопасное имя файла в каталоге."""
    safe = photos_storage.sanitize_filename(raw_name or "photo.bin")
    stem, ext = Path(safe).stem, (Path(safe).suffix.lower() or ".bin")
    fname = safe
    idx = 1
    while (target_dir / fname).exists():
        fname = f"{stem}-{idx}{ext}"
        idx += 1
        if idx > 9999:
            return f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
    return fname


async def _stage_upload_on_disk(
    f: UploadFile,
    folder: PhotoFolder,
    *,
    max_bytes: int,
    allowed_mime: set[str],
) -> tuple[Path, str, int, str | None]:
    """ФС-фаза загрузки: стримит во временный файл, переименовывает в final.

    Возвращает ``(final_path, filename, size, detected_mime)``. Никаких
    обращений к БД. При ошибке поднимает исключение и подчищает за собой
    (tmp удаляется автоматически в stream_upload_to_path при превышении
    лимита; final_path до удачного rename ещё не существует).
    """
    from app.api.photos import photo_service as _ps

    target_dir = photos_storage.folder_fs_path(folder.fs_path or folder.path)
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = target_dir / f"_tmp_{uuid.uuid4().hex}"
    written, detected_mime = await stream_upload_to_path(
        f, tmp_path, max_size=max_bytes, allowed_mimes=allowed_mime
    )
    fname = _ps._pick_unique_filename(target_dir, f.filename)
    final_path = target_dir / fname
    tmp_path.rename(final_path)
    return final_path, fname, written, detected_mime


async def _persist_uploaded_photo(
    db: AsyncSession,
    *,
    folder_id: uuid.UUID,
    user_id: uuid.UUID,
    filename: str,
    original_name: str,
    size: int,
    mime_type: str | None,
) -> Photo:
    """БД-фаза загрузки: создаёт строку Photo внутри savepoint."""
    async with db.begin_nested():
        photo = Photo(
            folder_id=folder_id,
            filename=filename,
            original_name=original_name,
            size_bytes=size,
            mime_type=mime_type,
            uploaded_by=user_id,
        )
        db.add(photo)
        await db.flush()
    return photo


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
    from app.api.photos import photo_service as _ps

    if not photos_storage.is_allowed_ext(f.filename or ""):
        return (
            None,
            0,
            None,
            UploadResultItem(
                original_name=f.filename or "?", ok=False, error="extension not allowed"
            ),
        )

    final_path: Path | None = None
    try:
        final_path, fname, size, detected_mime = await _ps._stage_upload_on_disk(
            f, folder, max_bytes=max_bytes, allowed_mime=allowed_mime
        )
        photo = await _ps._persist_uploaded_photo(
            db,
            folder_id=folder_id,
            user_id=user.id,
            filename=fname,
            original_name=f.filename or fname,
            size=size,
            mime_type=detected_mime or (f.content_type or "") or None,
        )
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


async def _validate_upload_context(
    db: AsyncSession,
    user: User,
    redis: Redis,
    folder_id: uuid.UUID,
) -> tuple[PhotoFolder, int, set[str]]:
    """Проверяет, что модуль включён, папка существует, у юзера есть права.

    Возвращает (folder, max_bytes, allowed_mime).
    """
    from app.api.photos import photo_service as _ps

    cfg = _ps._module_settings()
    if not cfg.enabled:
        raise HTTPException(status_code=503, detail="Photos module disabled")
    folder = await photo_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _ps.require_folder_permission(user, folder, PERM_UPLOADER, db, redis)
    max_bytes = (cfg.max_size_mb or 50) * 1024 * 1024
    allowed_mime = set(cfg.allowed_mime or [])
    return folder, max_bytes, allowed_mime


async def _finalize_uploaded_photos(
    request: Request,
    redis: Redis,
    user: User,
    folder_id: uuid.UUID,
    pending: list[tuple[Photo, int, Path]],
    items: list[UploadResultItem],
) -> None:
    """Post-commit: enqueue обработки + аудит + успешные result items."""
    from app.api.photos import photo_service as _ps

    for photo, size, _ in pending:
        await _ps._enqueue_processing(request, photo.id)
        await _ps._emit_audit(
            redis,
            event_type="photos.photo_uploaded",
            user_id=str(user.id),
            user_email=user.email,
            resource_id=str(photo.id),
            resource_title=photo.original_name,
            metadata={"folder_id": str(folder_id), "size_bytes": size},
        )
        items.append(
            UploadResultItem(photo_id=photo.id, original_name=photo.original_name, ok=True)
        )


def _rollback_uploaded_files(pending: list[tuple[Photo, int, Path]]) -> None:
    for _, _, path in pending:
        with contextlib.suppress(Exception):
            path.unlink(missing_ok=True)


async def perform_upload(
    db: AsyncSession,
    user: User,
    redis: Redis,
    request: Request,
    folder_id: uuid.UUID,
    files: list[UploadFile],
) -> UploadResult:
    from app.api.photos import photo_service as _ps

    folder, max_bytes, allowed_mime = await _ps._validate_upload_context(db, user, redis, folder_id)
    items: list[UploadResultItem] = []
    pending: list[tuple[Photo, int, Path]] = []

    for f in files:
        try:
            async with db.begin_nested():
                photo, size, final_path, err_item = await _ps._save_single_upload(
                    f,
                    folder,
                    folder_id,
                    user,
                    db,
                    max_bytes=max_bytes,
                    allowed_mime=allowed_mime,
                )
                if err_item is not None:
                    items.append(err_item)
                    raise ValueError(err_item.error or "Upload failed")
                if photo is not None and final_path is not None:
                    pending.append((photo, size, final_path))
        except Exception as exc:
            logger.warning("photos.upload.file_failed", filename=f.filename, error=str(exc))
            if not any(item.original_name == (f.filename or "?") for item in items):
                items.append(
                    UploadResultItem(original_name=f.filename or "?", ok=False, error=str(exc))
                )

    if not pending:
        return UploadResult(items=items)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        _ps._rollback_uploaded_files(pending)
        logger.exception("photos.upload_commit_failed", error=str(exc))
        for photo, _, _ in pending:
            items.append(
                UploadResultItem(
                    original_name=photo.original_name, ok=False, error="database error"
                )
            )
        return UploadResult(items=items)

    await _ps._finalize_uploaded_photos(request, redis, user, folder_id, pending, items)
    return UploadResult(items=items)
