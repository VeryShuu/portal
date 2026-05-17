"""Очистка корзины и истёкших ZIP-заданий."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder, PhotoTagAssignment, PhotoZipJob
from app.services import photos_storage

logger = get_logger(__name__)


async def cleanup_deleted_photos(ctx: dict) -> int:
    """Удаляет файлы и записи в БД для photos с deleted_at старше 30 дней."""
    cutoff = datetime.now(UTC) - timedelta(days=30)
    deleted = 0
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Photo).where(Photo.deleted_at.isnot(None), Photo.deleted_at < cutoff)
        )
        photos = res.scalars().all()
        for p in photos:
            try:
                folder_res = await db.execute(
                    select(PhotoFolder).where(PhotoFolder.id == p.folder_id)
                )
                folder = folder_res.scalar_one_or_none()
                original = None
                if folder:
                    original = (
                        photos_storage.folder_fs_path(folder.fs_path or folder.path) / p.filename
                    )
                photos_storage.delete_photo_files(original, p.id)
                await db.execute(
                    delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == p.id)
                )
                await db.execute(delete(Photo).where(Photo.id == p.id))
                deleted += 1
            except Exception as exc:
                logger.warning("photos.cleanup.failed", photo_id=str(p.id), error=str(exc))
        await db.commit()
    logger.info("photos.cleanup.done", count=deleted)
    return deleted


async def cleanup_zip_jobs(ctx: dict) -> None:
    """Удаляет истёкшие ZIP-задания (файлы и записи в БД)."""
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(PhotoZipJob).where(
                PhotoZipJob.expires_at.isnot(None),
                PhotoZipJob.expires_at < now,
            )
        )
        jobs = res.scalars().all()
        count = 0
        for job in jobs:
            if job.file_path:
                try:
                    p = Path(job.file_path)
                    if p.exists():
                        p.unlink()
                except OSError as exc:
                    logger.warning(
                        "photos.zip.cleanup_file_failed", job_id=str(job.id), error=str(exc)
                    )
            count += 1
        if jobs:
            await db.execute(
                delete(PhotoZipJob).where(
                    PhotoZipJob.expires_at.isnot(None),
                    PhotoZipJob.expires_at < now,
                )
            )
            await db.commit()
        logger.info("photos.zip.cleanup.done", count=count)


_TRASH_EMPTY_LOCK_KEY = "photos:trash_empty:lock"
_TRASH_EMPTY_BATCH = 500


async def empty_photo_trash(ctx: dict, triggered_by_user_id: str) -> dict:
    """Окончательно удаляет ВСЕ фото из корзины (запускается по запросу admin).

    Использует блокировку в Redis для предотвращения конкурентных запусков.
    Возвращает словарь {"purged": N} для логирования результата.
    """
    redis = ctx.get("redis")

    if redis is not None:
        acquired = await redis.set(_TRASH_EMPTY_LOCK_KEY, "1", nx=True, ex=3600)
        if not acquired:
            logger.warning("photos.trash.empty_already_running")
            return {"purged": 0, "skipped": "already_running"}

    try:
        purged = 0
        async with AsyncSessionLocal() as db:
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
                        logger.warning(
                            "photos.trash.empty_failed",
                            photo_id=str(photo.id),
                            error=str(exc),
                        )
                await db.execute(
                    delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id.in_(photo_ids))
                )
                await db.execute(delete(Photo).where(Photo.id.in_(photo_ids)))
                await db.commit()
                await asyncio.sleep(0)

        logger.info("photos.trash.emptied", purged=purged, triggered_by=triggered_by_user_id)

        if redis is not None:
            from app.services.audit import push_audit_event

            await push_audit_event(
                redis,
                event_type="photos.trash_emptied",
                user_id=triggered_by_user_id,
                resource_type="photo",
                resource_id="all",
                metadata={"purged": purged},
            )

        return {"purged": purged}
    finally:
        if redis is not None:
            await redis.delete(_TRASH_EMPTY_LOCK_KEY)
