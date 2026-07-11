"""Генерация ZIP-архивов целой папки фотогалереи."""

from __future__ import annotations

import uuid
import zipfile
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update

from app.core.database import AsyncSessionLocal
from app.core.logging import bind_request_context, get_logger
from app.models.photos import Photo, PhotoZipJob
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
            folders_res = await db.execute(
                text(
                    """
                    WITH RECURSIVE subfolders AS (
                        SELECT id, parent_id, name, fs_path, path
                        FROM photo_folders
                        WHERE id = :root_id AND deleted_at IS NULL
                        UNION ALL
                        SELECT f.id, f.parent_id, f.name, f.fs_path, f.path
                        FROM photo_folders f
                        INNER JOIN subfolders s ON f.parent_id = s.id
                        WHERE f.deleted_at IS NULL
                    )
                    SELECT id, parent_id, name, fs_path, path FROM subfolders
                    """
                ),
                {"root_id": job.folder_id},
            )
            folders = folders_res.fetchall()
            folders_by_id = {}
            for row in folders:
                fid = uuid.UUID(str(row.id)) if not isinstance(row.id, uuid.UUID) else row.id
                parent_id = (
                    uuid.UUID(str(row.parent_id))
                    if row.parent_id and not isinstance(row.parent_id, uuid.UUID)
                    else row.parent_id
                )
                folders_by_id[fid] = (fid, parent_id, row.name, row.fs_path, row.path)

            if not folders_by_id:
                raise ValueError("Папка не найдена")

            folder_ids = list(folders_by_id.keys())
            photos_res = await db.execute(
                select(Photo).where(
                    Photo.folder_id.in_(folder_ids),
                    Photo.deleted_at.is_(None),
                )
            )
            photos = photos_res.scalars().all()

            photos_storage.ZIPS_ROOT.mkdir(parents=True, exist_ok=True)
            zip_path = photos_storage.ZIPS_ROOT / f"{job_id}.zip"

            job_folder_id = (
                uuid.UUID(str(job.folder_id))
                if not isinstance(job.folder_id, uuid.UUID)
                else job.folder_id
            )

            memo: dict[uuid.UUID, str] = {}

            def get_relative_path(folder_id: uuid.UUID) -> str:
                fid = (
                    uuid.UUID(str(folder_id)) if not isinstance(folder_id, uuid.UUID) else folder_id
                )
                if fid == job_folder_id:
                    return ""
                if fid in memo:
                    return memo[fid]
                f = folders_by_id.get(fid)
                if not f:
                    return ""
                f_parent_id = f[1]
                if not f_parent_id:
                    return ""
                parent_rel = get_relative_path(f_parent_id)
                safe_name = photos_storage.sanitize_filename(f[2])
                res = f"{parent_rel}/{safe_name}" if parent_rel else safe_name
                memo[fid] = res
                return res

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for photo in photos:
                    try:
                        pfid = (
                            uuid.UUID(str(photo.folder_id))
                            if not isinstance(photo.folder_id, uuid.UUID)
                            else photo.folder_id
                        )
                        folder_row = folders_by_id.get(pfid)
                        if not folder_row:
                            continue
                        original_path = (
                            photos_storage.folder_fs_path(folder_row[3] or folder_row[4])
                            / photo.filename
                        )
                        if original_path.exists():
                            rel_dir = get_relative_path(pfid)
                            arcname = f"{rel_dir}/{photo.filename}" if rel_dir else photo.filename
                            zf.write(original_path, arcname)
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
            except Exception as exc:
                logger.debug("photos.zip.mark_error_failed", job_id=job_id, error=str(exc))
