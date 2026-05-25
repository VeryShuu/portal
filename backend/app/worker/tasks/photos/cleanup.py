from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.photos import PhotoZipJob
from app.services.photos_trash import TrashService

logger = get_logger(__name__)


async def cleanup_deleted_photos(ctx: dict) -> int:
    """Удаляет файлы и записи в БД для photos с deleted_at старше 30 дней."""

    async with AsyncSessionLocal() as db:
        stats = await TrashService.purge_expired(db, ttl_days=30)
    logger.info(
        "photos.cleanup.done",
        count=stats["purged_photos"],
        folders=stats["purged_folders"],
    )
    return stats["purged_photos"]


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
_TRASH_EMPTY_LOCK_TTL = 600  # 10 минут — заведомо больше реального времени работы, но не «навсегда»


async def empty_photo_trash(ctx: dict, triggered_by_user_id: str) -> dict:
    """Окончательно удаляет ВСЕ фото из корзины (запускается по запросу admin).

    Использует блокировку в Redis для предотвращения конкурентных запусков.
    Возвращает словарь {"purged": N} для логирования результата.
    """
    redis = ctx.get("redis")

    if redis is not None:
        acquired = await redis.set(_TRASH_EMPTY_LOCK_KEY, "1", nx=True, ex=_TRASH_EMPTY_LOCK_TTL)
        if not acquired:
            logger.warning("photos.trash.empty_already_running")
            return {"purged": 0, "skipped": "already_running"}

    try:
        async with AsyncSessionLocal() as db:
            stats = await TrashService.empty_trash(db)

        purged = stats["purged_photos"]
        folders_purged = stats["purged_folders"]

        logger.info(
            "photos.trash.emptied",
            purged=purged,
            folders=folders_purged,
            triggered_by=triggered_by_user_id,
        )

        if redis is not None:
            from app.services.audit import push_audit_event

            await push_audit_event(
                redis,
                event_type="photos.trash_emptied",
                user_id=triggered_by_user_id,
                resource_type="photo",
                resource_id="all",
                metadata={"purged": purged, "folders_purged": folders_purged},
            )

        return {"purged": purged, "folders_purged": folders_purged}
    finally:
        if redis is not None:
            await redis.delete(_TRASH_EMPTY_LOCK_KEY)
