"""Сканирование import-каталога и создание PhotoFolder / Photo записей."""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.logging import bind_request_context, get_logger
from app.models.photos import Photo, PhotoFolder
from app.services import photos_storage

logger = get_logger(__name__)

_IMPORT_FILE_LIMIT = 5_000
_IMPORT_BATCH_SIZE = 100


def _slugify_import(text_: str) -> str:
    norm = unicodedata.normalize("NFKD", text_).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", norm).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or "folder"


async def import_scan_run(ctx: dict, user_id: str) -> dict:
    bind_request_context(user_id=user_id)
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
    limit_reached = False

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
            new_path = f"{parent_path}/{slug}" if parent_path else slug
            existing = await db.scalar(select(PhotoFolder).where(PhotoFolder.path == new_path))
            if existing:
                folder_cache[abs_str] = existing
                return existing

            from app.api.photos import folder_service

            fs_seg = await folder_service.resolve_unique_fs_seg(db, name=name, parent_id=parent_id)
            parent_fs = (parent_folder.fs_path if parent_folder else "") or ""
            new_fs_path = f"{parent_fs}/{fs_seg}" if parent_fs else fs_seg

            new_folder = PhotoFolder(
                parent_id=parent_id,
                name=name,
                slug=slug,
                path=new_path,
                fs_path=new_fs_path,
                created_by=uid,
            )
            db.add(new_folder)
            await db.flush()
            new_folder_paths.add(abs_str)
            folder_cache[abs_str] = new_folder
            return new_folder

        pending_photos: list[Photo] = []
        committed_photo_ids: list[uuid.UUID] = []

        async def _flush_batch() -> None:
            """Сохраняет накопленные фото в БД, но НЕ enqueue'ит в worker'а.

            Enqueue в ARQ выполняется отдельно — строго после ``db.commit()``
            (см. ревью, находка #15: enqueue до commit может дать worker'у
            photo_id, которого после rollback в БД не окажется).

            Транзакционная гранулярность (#B-9): каждое фото добавляется
            в собственном SAVEPOINT (``db.begin_nested()``), чтобы ошибка
            на N-м файле (например, IntegrityError по UNIQUE-индексу или
            DataError) откатывала только этот файл, а не весь батч.
            """
            if not pending_photos:
                return
            for p in pending_photos:
                try:
                    async with db.begin_nested():
                        db.add(p)
                        await db.flush([p])
                    committed_photo_ids.append(p.id)
                except Exception as exc:
                    errors.append(f"photo {p.filename}: {exc}")
                    logger.warning(
                        "photos.import.flush_failed",
                        filename=p.filename,
                        folder_id=str(p.folder_id),
                        error=str(exc),
                    )
            pending_photos.clear()

        def _collect_walk(root: str) -> list[tuple[str, list[tuple[str, int]]]]:
            collected: list[tuple[str, list[tuple[str, int]]]] = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames.sort()
                files_with_size: list[tuple[str, int]] = []
                for fname in sorted(filenames):
                    try:
                        sz = os.stat(os.path.join(dirpath, fname)).st_size
                    except OSError:
                        sz = 0
                    files_with_size.append((fname, sz))
                collected.append((dirpath, files_with_size))
            return collected

        walk_entries = await asyncio.to_thread(_collect_walk, str(import_root))

        for dirpath, files_with_size in walk_entries:
            if limit_reached:
                break
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
            for filename, file_size in files_with_size:
                if photos_imported >= _IMPORT_FILE_LIMIT:
                    limit_reached = True
                    break
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

                    dest_dir = photos_storage.ORIGINALS_ROOT / folder.fs_path
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    src_file = abs_dir / filename
                    dest_file = dest_dir / filename

                    if not dest_file.exists():
                        import shutil

                        await asyncio.to_thread(shutil.move, str(src_file), str(dest_file))

                    photo = Photo(
                        folder_id=folder.id,
                        filename=filename,
                        original_name=filename,
                        size_bytes=file_size,
                        uploaded_by=uid,
                    )
                    pending_photos.append(photo)
                    photos_imported += 1
                    if len(pending_photos) >= _IMPORT_BATCH_SIZE:
                        await _flush_batch()
                except Exception as exc:
                    errors.append(f"{dirpath}/{filename}: {exc}")

        await _flush_batch()
        await db.commit()

    if pool is not None and committed_photo_ids:
        for pid in committed_photo_ids:
            try:
                await pool.enqueue_job(
                    "process_photo_upload",
                    str(pid),
                    _job_id=f"photos:process:{pid}",
                )
            except Exception as exc:
                logger.warning(
                    "photos.import.enqueue_failed",
                    photo_id=str(pid),
                    error=str(exc),
                )

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
        "limit_reached": limit_reached,
    }
