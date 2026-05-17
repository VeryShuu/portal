"""Генерация ZIP-архивов целой папки фотогалереи."""

from __future__ import annotations

import uuid
import zipfile
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.logging import bind_request_context, get_logger
from app.models.photos import Photo, PhotoFolder, PhotoZipJob
from app.services import photos_storage

logger = get_logger(__name__)


async def generate_folder_zip(ctx: dict, job_id: str) -> None:
    """Генерирует ZIP-архив всех фото папки и сохраняет на диск."""
    jid = uuid.UUID(job_id)
    async with AsyncSessionLocal() as db:
        job_res = await db.execute(select(PhotoZipJob).where(PhotoZipJob.id == jid))
        job = job_res.scalar_one_or_none()
        if not job:
            logger.warning("photos.zip.job_not_found", job_id=job_id)
            return
        if job.user_id:
            bind_request_context(user_id=str(job.user_id))

        await db.execute(
            update(PhotoZipJob).where(PhotoZipJob.id == jid).values(status="processing")
        )
        await db.commit()

        try:
            folder_res = await db.execute(
                select(PhotoFolder).where(PhotoFolder.id == job.folder_id)
            )
            folder = folder_res.scalar_one_or_none()
            if not folder:
                raise ValueError("Папка не найдена")

            photos_res = await db.execute(
                select(Photo).where(
                    Photo.folder_id == job.folder_id,
                    Photo.deleted_at.is_(None),
                )
            )
            photos = photos_res.scalars().all()

            photos_storage.ZIPS_ROOT.mkdir(parents=True, exist_ok=True)
            zip_path = photos_storage.ZIPS_ROOT / f"{job_id}.zip"

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for photo in photos:
                    try:
                        original_path = (
                            photos_storage.folder_fs_path(folder.fs_path or folder.path)
                            / photo.filename
                        )
                        if original_path.exists():
                            zf.write(original_path, photo.filename)
                    except Exception as exc:
                        logger.warning(
                            "photos.zip.skip_file",
                            photo_id=str(photo.id),
                            error=str(exc),
                        )

            expires = datetime.now(UTC) + timedelta(hours=24)
            await db.execute(
                update(PhotoZipJob)
                .where(PhotoZipJob.id == jid)
                .values(
                    status="done",
                    file_path=str(zip_path),
                    expires_at=expires,
                )
            )
            await db.commit()
            logger.info("photos.zip.done", job_id=job_id, path=str(zip_path))

        except Exception as exc:
            logger.exception("photos.zip.failed", job_id=job_id, error=str(exc))
            try:
                await db.execute(
                    update(PhotoZipJob)
                    .where(PhotoZipJob.id == jid)
                    .values(
                        status="error",
                        error=str(exc),
                    )
                )
                await db.commit()
            except Exception:
                pass
