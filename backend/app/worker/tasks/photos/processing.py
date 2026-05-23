"""Обработка загруженных фото: thumbnails, EXIF, detect-missing re-queue."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update

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

        if getattr(photo, "processed", False):
            thumb = photos_storage.THUMBS_ROOT / str(photo.id) / "200.webp"
            if await asyncio.to_thread(thumb.exists):
                logger.info("photos.process.already_processed", photo_id=photo_id)
                return

        folder_res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        folder = folder_res.scalar_one_or_none()
        if not folder:
            return

        original_path = (
            photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
        )
        if not original_path.exists():
            logger.warning(
                "photos.process.missing_original", photo_id=photo_id, path=str(original_path)
            )
            return

        thumb_ok = False
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, photos_storage.generate_thumbnails, pid, original_path)
            thumb_ok = True
        except Exception as exc:
            logger.exception("photos.process.thumb_failed", photo_id=photo_id, error=str(exc))

        try:
            from app.core.modules_config import load_modules

            strip_gps = load_modules().photos.strip_gps
        except Exception:
            strip_gps = True

        try:
            exif, size, taken_at_iso = photos_storage.extract_exif(
                original_path, strip_gps=strip_gps
            )
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
            with contextlib.suppress(Exception):
                values["taken_at"] = datetime.fromisoformat(taken_at_iso)
        await db.execute(update(Photo).where(Photo.id == pid).values(**values))
        await db.commit()
        logger.info("photos.processed", photo_id=photo_id)


async def detect_missing_thumbnails(ctx: dict) -> dict:
    """Находит обработанные фото без thumbnail 200 и ставит их в очередь повторно.
    Также находит необработанные фото (processed=False), загруженные более 10
    минут назад, и рекьюит их.
    """
    requeued = 0
    pool = ctx.get("redis")
    if pool is None:
        logger.warning("photos.detect_missing.no_redis_pool")
        return {"requeued": 0}

    cutoff = datetime.now(UTC) - timedelta(minutes=10)

    async with AsyncSessionLocal() as db:
        batch_size = 500
        offset = 0
        while True:
            res = await db.execute(
                select(Photo)
                .where(
                    Photo.deleted_at.is_(None),
                    or_(
                        Photo.processed.is_(True),
                        and_(Photo.processed.is_(False), Photo.created_at < cutoff),
                    ),
                )
                .order_by(Photo.id)
                .limit(batch_size)
                .offset(offset)
            )
            photos_batch = res.scalars().all()
            if not photos_batch:
                break

            for photo in photos_batch:
                is_processed = getattr(photo, "processed", True)
                should_requeue = False
                if not is_processed:
                    should_requeue = True
                else:
                    thumb = photos_storage.THUMBS_ROOT / str(photo.id) / "200.webp"
                    if not await asyncio.to_thread(thumb.exists):
                        should_requeue = True

                if should_requeue:
                    try:
                        await pool.enqueue_job(
                            "process_photo_upload",
                            str(photo.id),
                            _job_id=f"photos:process:{photo.id}",
                        )
                        requeued += 1
                    except Exception as exc:
                        logger.warning(
                            "photos.detect_missing.enqueue_failed",
                            photo_id=str(photo.id),
                            error=str(exc),
                        )

            if len(photos_batch) < batch_size:
                break
            offset += batch_size
    logger.info("photos.detect_missing.done", requeued=requeued)
    return {"requeued": requeued}
