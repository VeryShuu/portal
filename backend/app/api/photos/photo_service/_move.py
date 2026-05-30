from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photos import Photo, PhotoFolder
from app.services import photos_photo_repo as photo_repo
from app.services import photos_storage

from .._common import logger


def _move_photo_file_on_disk(
    photo: Photo,
    src_folder: PhotoFolder | None,
    target_folder: PhotoFolder,
    moved_files: list[tuple[str, str]],
) -> None:
    """Перемещает оригинал фото на диске из src в target.

    Накапливает ``moved_files`` (dst, src) для возможного отката при сбое
    транзакции. Если файл-конфликт — присваивает новое уникальное имя и
    обновляет ``photo.filename``. Если src отсутствует — no-op (БД-only
    move допустим, файл подберётся auto-heal-задачей).
    """
    if src_folder is None:
        return
    src_dir = photos_storage.folder_fs_path(src_folder.fs_path or src_folder.path)
    dst_dir = photos_storage.folder_fs_path(target_folder.fs_path or target_folder.path)
    dst_dir.mkdir(parents=True, exist_ok=True)
    src_file = src_dir / photo.filename
    dst_file = dst_dir / photo.filename
    if not src_file.exists():
        return
    if not dst_file.exists():
        shutil.move(str(src_file), str(dst_file))
        moved_files.append((str(dst_file), str(src_file)))
        return
    stem = Path(photo.filename).stem
    ext = Path(photo.filename).suffix
    candidate = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
    new_dst = str(dst_dir / candidate)
    shutil.move(str(src_file), new_dst)
    moved_files.append((new_dst, str(src_file)))
    photo.filename = candidate


async def move_photo_to_folder(
    db: AsyncSession,
    photo: Photo,
    target_folder: PhotoFolder,
) -> None:
    """Перемещает фото в другую папку синхронно (DB + ФС) с откатом при сбое.

    Используется PATCH /photos/{id}. ACL вызывающий код должен проверить ДО
    вызова. Коммитит транзакцию сам; при ошибке коммита возвращает файлы
    на место и пробрасывает исключение.
    """
    from app.api.photos import photo_service as _ps

    src_folder = await photo_repo.fetch_folder(db, photo.folder_id)
    moved_files: list[tuple[str, str]] = []
    _ps._move_photo_file_on_disk(photo, src_folder, target_folder, moved_files)
    photo.folder_id = target_folder.id
    await _ps._commit_bulk_or_revert_files(db, moved_files)


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
