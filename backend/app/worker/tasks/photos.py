"""ARQ задачи модуля фотогалереи."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import unicodedata
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, update

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder, PhotoTagAssignment, PhotoZipJob
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
            with contextlib.suppress(Exception):
                values["taken_at"] = datetime.fromisoformat(taken_at_iso)
        await db.execute(update(Photo).where(Photo.id == pid).values(**values))
        await db.commit()
        logger.info("photos.processed", photo_id=photo_id)


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


async def generate_folder_zip(ctx: dict, job_id: str) -> None:
    """Генерирует ZIP-архив всех фото папки и сохраняет на диск."""
    jid = uuid.UUID(job_id)
    async with AsyncSessionLocal() as db:
        job_res = await db.execute(select(PhotoZipJob).where(PhotoZipJob.id == jid))
        job = job_res.scalar_one_or_none()
        if not job:
            logger.warning("photos.zip.job_not_found", job_id=job_id)
            return

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


async def detect_missing_thumbnails(ctx: dict) -> dict:
    """Находит обработанные фото без thumbnail 200 и ставит их в очередь повторно."""
    requeued = 0
    pool = ctx.get("redis")
    async with AsyncSessionLocal() as db:
        batch_size = 500
        offset = 0
        while True:
            res = await db.execute(
                select(Photo)
                .where(
                    Photo.processed.is_(True),
                    Photo.deleted_at.is_(None),
                )
                .order_by(Photo.id)
                .limit(batch_size)
                .offset(offset)
            )
            photos_batch = res.scalars().all()
            if not photos_batch:
                break

            for photo in photos_batch:
                thumb = photos_storage.THUMBS_ROOT / str(photo.id) / "200.webp"
                if not thumb.exists() and pool is not None:
                    try:
                        await pool.enqueue_job("process_photo_upload", str(photo.id))
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


def _slugify_import(text_: str) -> str:
    norm = unicodedata.normalize("NFKD", text_).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", norm).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or "folder"


async def import_scan_run(ctx: dict, user_id: str) -> dict:
    uid = uuid.UUID(user_id)
    import_root = photos_storage.IMPORT_ROOT
    if not import_root.exists():
        return {"error": "Import directory not found"}

    folders_created = 0
    photos_imported = 0
    skipped = 0
    errors: list[str] = []
    folder_cache: dict[str, PhotoFolder] = {}
    new_folder_paths: set[str] = set()
    pool = ctx.get("redis")

    async with AsyncSessionLocal() as db:

        async def _get_or_create_folder(abs_dir: Path) -> PhotoFolder | None:
            abs_str = str(abs_dir)
            if abs_str in folder_cache:
                return folder_cache[abs_str]
            rel = abs_dir.relative_to(import_root)
            parts = list(rel.parts)
            if not parts:
                return None
            parent_folder: PhotoFolder | None = None
            if len(parts) > 1:
                parent_folder = await _get_or_create_folder(abs_dir.parent)
                if parent_folder is None:
                    return None
            name = abs_dir.name
            slug = _slugify_import(name)
            parent_id = parent_folder.id if parent_folder else None
            parent_path = (parent_folder.path or parent_folder.slug) if parent_folder else ""
            existing = await db.scalar(select(PhotoFolder).where(PhotoFolder.fs_path == abs_str))
            if existing:
                folder_cache[abs_str] = existing
                return existing
            base_slug = slug
            i = 1
            while True:
                cnt = await db.scalar(
                    select(func.count(PhotoFolder.id)).where(
                        PhotoFolder.parent_id == parent_id,
                        PhotoFolder.slug == slug,
                        PhotoFolder.deleted_at.is_(None),
                    )
                )
                if not cnt:
                    break
                i += 1
                slug = f"{base_slug}-{i}"
                if i > 9999:
                    slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                    break
            new_path = f"{parent_path}/{slug}" if parent_path else slug
            new_folder = PhotoFolder(
                parent_id=parent_id,
                name=name,
                slug=slug,
                path=new_path,
                fs_path=abs_str,
                created_by=uid,
            )
            db.add(new_folder)
            await db.flush()
            new_folder_paths.add(abs_str)
            folder_cache[abs_str] = new_folder
            return new_folder

        for dirpath, dirnames, filenames in os.walk(str(import_root)):
            dirnames.sort()
            abs_dir = Path(dirpath)
            if abs_dir == import_root:
                continue
            try:
                folder = await _get_or_create_folder(abs_dir)
                if folder is None:
                    continue
                if str(abs_dir) in new_folder_paths:
                    folders_created += 1
            except Exception as exc:
                errors.append(f"folder {dirpath}: {exc}")
                continue
            for filename in sorted(filenames):
                if not photos_storage.is_allowed_ext(filename):
                    skipped += 1
                    continue
                try:
                    folder = folder_cache.get(str(abs_dir))
                    if folder is None:
                        skipped += 1
                        continue
                    existing_photo = await db.scalar(
                        select(func.count(Photo.id)).where(
                            Photo.folder_id == folder.id,
                            Photo.filename == filename,
                        )
                    )
                    if existing_photo:
                        skipped += 1
                        continue
                    file_size = (abs_dir / filename).stat().st_size
                    photo = Photo(
                        folder_id=folder.id,
                        filename=filename,
                        original_name=filename,
                        size_bytes=file_size,
                        uploaded_by=uid,
                    )
                    db.add(photo)
                    await db.flush()
                    if pool is not None:
                        try:
                            await pool.enqueue_job("process_photo_upload", str(photo.id))
                        except Exception as exc:
                            logger.warning(
                                "photos.import.enqueue_failed",
                                photo_id=str(photo.id),
                                error=str(exc),
                            )
                    photos_imported += 1
                except Exception as exc:
                    errors.append(f"{dirpath}/{filename}: {exc}")
        await db.commit()
    logger.info(
        "photos.import.done",
        folders_created=folders_created,
        photos_imported=photos_imported,
        skipped=skipped,
    )
    return {
        "folders_created": folders_created,
        "photos_imported": photos_imported,
        "skipped": skipped,
        "errors": errors,
    }
