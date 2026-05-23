from __future__ import annotations

import asyncio
import contextlib
import shutil
import uuid
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.photos import folder_repo, photo_repo
from app.api.photos._common import _photo_to_public
from app.core.constants import PERM_MANAGER
from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder, PhotoTagAssignment
from app.models.user import User
from app.schemas.photos import PhotoList, PhotoPublic
from app.services import photos_storage
from app.services.photos_acl import perm_gte, resolve_folder_permission

logger = get_logger(__name__)


class TrashService:
    @staticmethod
    async def soft_delete_folder(db: AsyncSession, folder_id: uuid.UUID) -> int:
        """Мягко удаляет папку, все подпапки и все фотографии в них."""
        folder = await folder_repo.fetch_active_folder(db, folder_id)
        if not folder:
            return 0

        delete_ts = datetime.now(UTC)
        folder.deleted_at = delete_ts

        descendant_ids = await folder_repo.fetch_descendant_ids(db, folder_id)
        if descendant_ids:
            # Soft delete all descendant folders
            await db.execute(
                update(PhotoFolder)
                .where(PhotoFolder.id.in_(descendant_ids), PhotoFolder.deleted_at.is_(None))
                .values(deleted_at=delete_ts)
            )
            # Soft delete all photos in descendant folders
            await db.execute(
                update(Photo)
                .where(Photo.folder_id.in_(descendant_ids), Photo.deleted_at.is_(None))
                .values(deleted_at=delete_ts)
            )

        await folder_repo.soft_delete_folder_photos(db, folder_id=folder_id, ts=delete_ts)
        await db.commit()
        return 1 + len(descendant_ids)

    @staticmethod
    async def soft_delete_photo(db: AsyncSession, photo_id: uuid.UUID) -> None:
        """Мягко удаляет одну фотографию."""
        photo = await photo_repo.fetch_active_photo(db, photo_id)
        if not photo:
            return
        TrashService.mark_photo_deleted(photo)
        await db.commit()

    @staticmethod
    def mark_photo_deleted(photo: Photo) -> None:
        """Помечает уже загруженную фотографию как удалённую без commit'а.

        Используется в bulk-операциях, где commit делается на уровне всей пачки.
        """
        photo.deleted_at = datetime.now(UTC)

    @staticmethod
    async def restore_folder(db: AsyncSession, folder_id: uuid.UUID) -> int:
        """Восстанавливает папку, ее подпапки и фотографии (сопоставляя метку удаления)."""
        folder = await folder_repo.fetch_folder_any(db, folder_id)
        if not folder or folder.deleted_at is None:
            return 0

        cascade_ts = folder.deleted_at
        folder.deleted_at = None

        descendant_ids = await folder_repo.fetch_descendant_ids(db, folder_id)
        await folder_repo.restore_descendants(
            db, descendant_ids=descendant_ids, cascade_ts=cascade_ts
        )
        await folder_repo.restore_direct_photos(db, folder_id=folder_id, cascade_ts=cascade_ts)

        await db.commit()
        return 1 + len(descendant_ids)

    @staticmethod
    async def restore_photo(db: AsyncSession, photo_id: uuid.UUID) -> None:
        """Восстанавливает одну фотографию."""
        photo = await photo_repo.fetch_photo_any(db, photo_id)
        if not photo or photo.deleted_at is None:
            return
        photo.deleted_at = None
        await db.commit()

    @staticmethod
    async def purge_photo(db: AsyncSession, photo_id: uuid.UUID) -> None:
        """Окончательно удаляет одну фотографию."""
        photo = await photo_repo.fetch_photo_any(db, photo_id)
        if not photo:
            return
        folder = await photo_repo.fetch_folder(db, photo.folder_id)
        original = None
        if folder:
            original = photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
        await asyncio.to_thread(photos_storage.delete_photo_files, original, photo.id)
        await photo_repo.purge_photo_row(db, photo.id)
        await db.commit()

    @staticmethod
    async def purge_folder_subtree(db: AsyncSession, folder_id: uuid.UUID) -> tuple[int, int]:
        """Окончательно удаляет папку со всеми подпапками, фотографиями и файлами на диске."""
        folder = await folder_repo.fetch_folder_any(db, folder_id)
        if not folder:
            return 0, 0

        descendant_ids = await folder_repo.fetch_descendant_ids(db, folder.id)
        all_folder_ids: list[uuid.UUID] = [folder.id, *descendant_ids]

        photos = await folder_repo.fetch_photos_in_folders(db, all_folder_ids)
        folders_for_fs = await folder_repo.fetch_folders_by_ids(db, descendant_ids)

        folder_by_id: dict[uuid.UUID, PhotoFolder] = {folder.id: folder}
        for sub in folders_for_fs:
            folder_by_id[sub.id] = sub

        for photo in photos:
            try:
                owner = folder_by_id.get(photo.folder_id)
                original = None
                if owner:
                    with contextlib.suppress(ValueError):
                        original = (
                            photos_storage.folder_fs_path(owner.fs_path or owner.path)
                            / photo.filename
                        )
                await asyncio.to_thread(photos_storage.delete_photo_files, original, photo.id)
            except Exception as exc:
                logger.warning(
                    "photos.purge_folder.photo_file_failed",
                    photo_id=str(photo.id),
                    error=str(exc),
                )

        try:
            fs_dir = photos_storage.folder_fs_path(folder.fs_path or folder.path)
        except ValueError:
            fs_dir = None
        if fs_dir is not None and fs_dir.exists():
            try:
                await asyncio.to_thread(shutil.rmtree, str(fs_dir), True)
            except Exception as exc:
                logger.warning(
                    "photos.purge_folder.fs_rmtree_failed",
                    folder_id=str(folder.id),
                    path=str(fs_dir),
                    error=str(exc),
                )

        # Удаление записей из базы данных снизу вверх (RESTRICT)
        ordered = sorted(
            folder_by_id.values(),
            key=lambda f: len((f.path or "").split("/")),
            reverse=True,
        )
        for f in ordered:
            await db.execute(delete(PhotoFolder).where(PhotoFolder.id == f.id))
        await db.commit()

        return len(all_folder_ids), len(photos)

    @staticmethod
    async def purge_expired(db: AsyncSession, ttl_days: int = 30) -> dict:
        """Очищает элементы из корзины (фото и папки) старше заданного TTL."""
        cutoff = datetime.now(UTC) - timedelta(days=ttl_days)
        deleted_photos_count = 0

        # 1. Зачистка истекших фото
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
                await asyncio.to_thread(photos_storage.delete_photo_files, original, p.id)
                await db.execute(
                    delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == p.id)
                )
                await db.execute(delete(Photo).where(Photo.id == p.id))
                deleted_photos_count += 1
            except Exception as exc:
                logger.warning("photos.cleanup.failed", photo_id=str(p.id), error=str(exc))
        await db.commit()

        # 2. Зачистка истекших папок
        res_roots = await db.execute(
            select(PhotoFolder).where(
                PhotoFolder.deleted_at.isnot(None),
                PhotoFolder.deleted_at < cutoff,
                PhotoFolder.parent_id.is_(None),
            )
        )
        roots = res_roots.scalars().all()

        res_non_roots = await db.execute(
            select(PhotoFolder).where(
                PhotoFolder.deleted_at.isnot(None),
                PhotoFolder.deleted_at < cutoff,
                PhotoFolder.parent_id.isnot(None),
            )
        )
        non_roots = res_non_roots.scalars().all()

        targets: list[PhotoFolder] = list(roots)
        if non_roots:
            active_ids_res = await db.execute(
                select(PhotoFolder.id).where(PhotoFolder.deleted_at.is_(None))
            )
            active_ids = {row[0] for row in active_ids_res.all()}
            for f in non_roots:
                if f.parent_id in active_ids:
                    targets.append(f)

        purged_folders_count = 0
        for folder in targets:
            try:
                purged_f, purged_p = await TrashService.purge_folder_subtree(db, folder.id)
                purged_folders_count += purged_f
                deleted_photos_count += purged_p
            except Exception as exc:
                logger.warning(
                    "photos.cleanup.folder_failed",
                    folder_id=str(folder.id),
                    error=str(exc),
                )
        return {"purged_photos": deleted_photos_count, "purged_folders": purged_folders_count}

    @staticmethod
    async def empty_trash(db: AsyncSession) -> dict[str, int]:
        """Окончательно удаляет ВСЕ элементы из корзины (фото и папки) без учета TTL."""
        deleted_photos_count = 0

        # 1. Зачистка всех удаленных фото
        res = await db.execute(select(Photo).where(Photo.deleted_at.isnot(None)))
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
                await asyncio.to_thread(photos_storage.delete_photo_files, original, p.id)
                await db.execute(
                    delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == p.id)
                )
                await db.execute(delete(Photo).where(Photo.id == p.id))
                deleted_photos_count += 1
            except Exception as exc:
                logger.warning("photos.cleanup.failed", photo_id=str(p.id), error=str(exc))
        await db.commit()

        # 2. Зачистка всех удаленных папок
        res_folders = await db.execute(
            select(PhotoFolder).where(PhotoFolder.deleted_at.isnot(None))
        )
        folders = res_folders.scalars().all()
        trash_ids = {f.id for f in folders}
        roots = [f for f in folders if f.parent_id not in trash_ids]

        purged_folders_count = 0
        for folder in roots:
            try:
                purged_f, purged_p = await TrashService.purge_folder_subtree(db, folder.id)
                purged_folders_count += purged_f
                deleted_photos_count += purged_p
            except Exception as exc:
                logger.warning(
                    "photos.cleanup.folder_failed",
                    folder_id=str(folder.id),
                    error=str(exc),
                )
        return {"purged_photos": deleted_photos_count, "purged_folders": purged_folders_count}

    @staticmethod
    async def list_trashed_folders(db: AsyncSession) -> list[PhotoFolder]:
        """Возвращает все удаленные папки."""
        return list(await folder_repo.fetch_deleted_folders_ordered(db))

    @staticmethod
    async def list_trashed_photos(
        db: AsyncSession, user: User, redis: Redis, *, page: int, per_page: int
    ) -> PhotoList:
        """Возвращает список удаленных фотографий, доступных пользователю."""
        cutoff = datetime.now(UTC) - timedelta(days=30)
        offset = (page - 1) * per_page

        if user.role == "admin":
            total = await photo_repo.count_deleted_photos_admin(db, cutoff)
            rows = await photo_repo.fetch_deleted_photos_admin_page(
                db, cutoff, offset=offset, limit=per_page
            )
            items = [
                _photo_to_public(photo, folder_path=folder.path if folder else None)
                for photo, folder in rows
            ]
            return PhotoList(items=items, total=total, page=page, per_page=per_page)

        all_rows = await photo_repo.fetch_deleted_photos_with_folders(db, cutoff)

        unique_folders: dict[uuid.UUID, PhotoFolder] = {}
        for _photo, folder in all_rows:
            if folder is not None and folder.id not in unique_folders:
                unique_folders[folder.id] = folder

        folder_perm_cache: dict[uuid.UUID, str | None] = {}
        for folder_id_key, folder in unique_folders.items():
            folder_perm_cache[folder_id_key] = await resolve_folder_permission(
                user, folder, db, redis
            )

        accessible_items: list[PhotoPublic] = []
        for photo, folder in all_rows:
            if folder is None:
                continue
            perm = folder_perm_cache.get(folder.id)
            if not perm_gte(perm, PERM_MANAGER):
                continue
            accessible_items.append(_photo_to_public(photo, folder_path=folder.path))

        total = len(accessible_items)
        items = accessible_items[offset : offset + per_page]
        return PhotoList(items=items, total=total, page=page, per_page=per_page)
