"""FS-операции корзины фотогалереи (без БД и без транзакций).

Выделено из ``photos_trash.py`` для разделения ответственностей
(см. ревью, находка #7: repo / file-service / orchestrator).
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from pathlib import Path

from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder
from app.services import photos_storage

logger = get_logger(__name__)


def _original_path_for(photo: Photo, folder: PhotoFolder | None) -> Path | None:
    if folder is None:
        return None
    try:
        return photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
    except ValueError:
        return None


async def delete_photo_files(photo: Photo, folder: PhotoFolder | None) -> None:
    """Удаляет с диска оригинал и thumbnails одного фото."""
    original = _original_path_for(photo, folder)
    await asyncio.to_thread(photos_storage.delete_photo_files, original, photo.id)


async def delete_many_photo_files(
    photos: list[Photo], folder_by_id: dict
) -> None:
    """Удаляет файлы пачки фото; ошибки логирует, но не пробрасывает."""
    for p in photos:
        try:
            await delete_photo_files(p, folder_by_id.get(p.folder_id))
        except Exception as exc:
            logger.warning(
                "photos.trash.photo_file_failed",
                photo_id=str(p.id),
                error=str(exc),
            )


async def rmtree_folder_fs(folder: PhotoFolder) -> None:
    """Рекурсивно удаляет каталог папки с диска. Ошибки логирует."""
    try:
        fs_dir = photos_storage.folder_fs_path(folder.fs_path or folder.path)
    except ValueError:
        return
    if not fs_dir.exists():
        return
    try:
        await asyncio.to_thread(shutil.rmtree, str(fs_dir), True)
    except Exception as exc:
        logger.warning(
            "photos.trash.fs_rmtree_failed",
            folder_id=str(folder.id),
            path=str(fs_dir),
            error=str(exc),
        )


__all__ = [
    "delete_photo_files",
    "delete_many_photo_files",
    "rmtree_folder_fs",
]
