"""ARQ задачи модуля фотогалереи."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder
from app.services import photos_storage

logger = get_logger(__name__)


async def process_photo_upload(ctx: dict, photo_id: str) -> None:
    """Генерирует thumbnails, извлекает EXIF, обновляет метаданные фото."""
    pid = uuid.UUID(photo_id)
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Photo).where(Photo.id == pid))
        photo = res.scalar_one_or_none()
        if not photo or photo.deleted_at is not None:
            return
        folder_res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        folder = folder_res.scalar_one_or_none()
        if not folder:
            return

        original_path = photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
        if not original_path.exists():
            logger.warning("photos.process.missing_original", photo_id=photo_id, path=str(original_path))
            return

        thumb_ok = False
        try:
            photos_storage.generate_thumbnails(pid, original_path)
            thumb_ok = True
        except Exception as exc:
            logger.exception("photos.process.thumb_failed", photo_id=photo_id, error=str(exc))

        try:
            exif, size, taken_at_iso = photos_storage.extract_exif(original_path, strip_gps=True)
        except Exception as exc:
            logger.exception("photos.process.exif_failed", photo_id=photo_id, error=str(exc))
            exif, size, taken_at_iso = {}, None, None

        values: dict = {"processed": thumb_ok}
        if size:
            values["width"] = size[0]
            values["height"] = size[1]
        if exif:
            values["exif"] = exif
        if taken_at_iso:
            try:
                values["taken_at"] = datetime.fromisoformat(taken_at_iso)
            except Exception:
                pass
        await db.execute(update(Photo).where(Photo.id == pid).values(**values))
        await db.commit()
        logger.info("photos.processed", photo_id=photo_id)


async def cleanup_deleted_photos(ctx: dict) -> int:
    """Удаляет файлы для photos с deleted_at старше 30 дней."""
    cutoff = datetime.now(UTC) - timedelta(days=30)
    deleted = 0
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Photo).where(Photo.deleted_at.isnot(None), Photo.deleted_at < cutoff)
        )
        photos = res.scalars().all()
        for p in photos:
            try:
                folder_res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == p.folder_id))
                folder = folder_res.scalar_one_or_none()
                original = None
                if folder:
                    original = photos_storage.folder_fs_path(folder.fs_path or folder.path) / p.filename
                photos_storage.delete_photo_files(original, p.id)
                deleted += 1
            except Exception as exc:
                logger.warning("photos.cleanup.failed", photo_id=str(p.id), error=str(exc))
    logger.info("photos.cleanup.done", count=deleted)
    return deleted
