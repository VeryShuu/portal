"""Сервис корзины фотогалереи (orchestrator).

Разделение ответственностей (см. ревью, находки #7, #B-3):

- ``photos_trash_files`` — операции с ФС (удаление файлов / каталогов).
- ``photos_trash_repo`` — узкоспециализированные DB-запросы для trash-сценариев.
- ``photos_trash`` (этот модуль) — оркестрирует ACL + изменения сущностей + аудит.

Контракт по транзакциям (#B-3):

- *Leaf*-методы (``soft_delete_folder``, ``soft_delete_photo``,
  ``restore_folder``, ``restore_photo``, ``purge_photo``,
  ``purge_folder_subtree``) НЕ вызывают ``db.commit()``. Коммит делает
  вызывающий код (роутер / worker / orchestrator-метод). Это позволяет
  тестировать leaf-методы внутри одной транзакции без сайд-эффектов и
  объединять их в составные операции на стороне caller'а.
- *Orchestrator*-методы (``purge_expired``, ``empty_trash``,
  ``empty_trash_for_user``) обрабатывают каждый элемент в собственном
  ``try/except``, поэтому коммитят результат на каждой успешной итерации
  как явную «batch-границу» — иначе ошибка на N-м элементе сломала бы
  сессию и заблокировала остальные.

ACL (#B-2): резолв прав по списку папок (``empty_trash_for_user``,
``list_trashed_photos``) идёт через ``resolve_folders_permissions_batch``,
а не циклом по ``resolve_folder_permission`` — это даёт один CTE на все
папки + pipelined ``MGET`` по Redis-кэшу вместо N round-trip'ов.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PERM_MANAGER
from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder
from app.models.user import User
from app.schemas.photos import PhotoList, PhotoPublic
from app.services import (
    photos_folder_repo as folder_repo,
)
from app.services import (
    photos_photo_repo as photo_repo,
)
from app.services import (
    photos_trash_files as trash_files,
)
from app.services import (
    photos_trash_repo as trash_repo,
)
from app.services.photos_acl import (
    perm_gte,
    resolve_folders_permissions_batch,
)
from app.services.photos_serializers import photo_to_public

logger = get_logger(__name__)


class TrashService:
    @staticmethod
    async def soft_delete_folder(db: AsyncSession, folder_id: uuid.UUID) -> int:
        """Мягко удаляет папку, все подпапки и все фотографии в них.

        Не коммитит — caller обязан вызвать ``db.commit()``.
        """
        folder = await folder_repo.fetch_active_folder(db, folder_id)
        if not folder:
            return 0

        delete_ts = datetime.now(UTC)
        folder.deleted_at = delete_ts

        descendant_ids = await folder_repo.fetch_descendant_ids(db, folder_id)
        if descendant_ids:
            await db.execute(
                update(PhotoFolder)
                .where(PhotoFolder.id.in_(descendant_ids), PhotoFolder.deleted_at.is_(None))
                .values(deleted_at=delete_ts)
            )
            await db.execute(
                update(Photo)
                .where(Photo.folder_id.in_(descendant_ids), Photo.deleted_at.is_(None))
                .values(deleted_at=delete_ts)
            )

        await folder_repo.soft_delete_folder_photos(db, folder_id=folder_id, ts=delete_ts)
        return 1 + len(descendant_ids)

    @staticmethod
    async def soft_delete_photo(db: AsyncSession, photo_id: uuid.UUID) -> None:
        """Мягко удаляет одну фотографию. Не коммитит."""
        photo = await photo_repo.fetch_active_photo(db, photo_id)
        if not photo:
            return
        TrashService.mark_photo_deleted(photo)

    @staticmethod
    def mark_photo_deleted(photo: Photo) -> None:
        """Помечает уже загруженную фотографию как удалённую без commit'а.

        Используется в bulk-операциях, где commit делается на уровне всей пачки.
        """
        photo.deleted_at = datetime.now(UTC)

    @staticmethod
    async def restore_folder(db: AsyncSession, folder_id: uuid.UUID) -> int:
        """Восстанавливает папку и подпапки/фото, удалённые тем же каскадом.

        Не коммитит.
        """
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
        return 1 + len(descendant_ids)

    @staticmethod
    async def restore_photo(db: AsyncSession, photo_id: uuid.UUID) -> None:
        """Снимает с фото пометку удаления. Не коммитит."""
        photo = await photo_repo.fetch_photo_any(db, photo_id)
        if not photo or photo.deleted_at is None:
            return
        photo.deleted_at = None

    @staticmethod
    async def purge_photo(db: AsyncSession, photo_id: uuid.UUID) -> None:
        """Окончательно удаляет файлы и запись фото. Не коммитит."""
        photo = await photo_repo.fetch_photo_any(db, photo_id)
        if not photo:
            return
        folder = await photo_repo.fetch_folder(db, photo.folder_id)
        await trash_files.delete_photo_files(photo, folder)
        await trash_repo.purge_photo_row(db, photo.id)

    @staticmethod
    async def purge_folder_subtree(db: AsyncSession, folder_id: uuid.UUID) -> tuple[int, int]:
        """Окончательно удаляет папку и всё поддерево (БД + ФС). Не коммитит."""
        folder = await folder_repo.fetch_folder_any(db, folder_id)
        if not folder:
            return 0, 0

        descendant_ids = await folder_repo.fetch_descendant_ids(db, folder.id)
        all_folder_ids: list[uuid.UUID] = [folder.id, *descendant_ids]

        photos = list(await folder_repo.fetch_photos_in_folders(db, all_folder_ids))
        folders_for_fs = await folder_repo.fetch_folders_by_ids(db, descendant_ids)

        folder_by_id: dict[uuid.UUID, PhotoFolder] = {folder.id: folder}
        for sub in folders_for_fs:
            folder_by_id[sub.id] = sub

        await trash_files.delete_many_photo_files(photos, folder_by_id)
        await trash_files.rmtree_folder_fs(folder)

        ordered = sorted(
            folder_by_id.values(),
            key=lambda f: len((f.path or "").split("/")),
            reverse=True,
        )
        for f in ordered:
            await trash_repo.delete_folder_row(db, f.id)

        return len(all_folder_ids), len(photos)

    @staticmethod
    async def _purge_photo_rows(db: AsyncSession, photos: list[Photo]) -> int:
        """Общая логика purge-цикла для `purge_expired` и `empty_trash` (#8).

        Удаляет файлы каждого фото и записи (Photo + tag assignments). Коммит
        делает orchestrator-вызывающий метод, поскольку батч обрабатывается
        как единая «транзакция-граница».
        """
        deleted = 0
        folder_ids = {p.folder_id for p in photos if p.folder_id is not None}
        folders_by_id = await photo_repo.fetch_folders_map(db, folder_ids)
        for p in photos:
            try:
                await trash_files.delete_photo_files(p, folders_by_id.get(p.folder_id))
                await trash_repo.purge_photo_row(db, p.id)
                deleted += 1
            except Exception as exc:
                logger.warning("photos.cleanup.failed", photo_id=str(p.id), error=str(exc))
        return deleted

    @staticmethod
    async def purge_expired(db: AsyncSession, ttl_days: int = 30) -> dict[str, int]:
        """Удаляет всё, что в корзине дольше ``ttl_days``.

        Orchestrator: коммитит на каждой успешной batch-границе, чтобы
        ошибка на отдельной папке не ломала всю сессию.
        """
        cutoff = datetime.now(UTC) - timedelta(days=ttl_days)

        photos = await trash_repo.fetch_expired_photos(db, cutoff)
        deleted_photos_count = await TrashService._purge_photo_rows(db, photos)
        await db.commit()

        roots = await trash_repo.fetch_expired_root_folders(db, cutoff)
        non_roots = await trash_repo.fetch_expired_non_root_folders(db, cutoff)

        targets: list[PhotoFolder] = list(roots)
        if non_roots:
            active_ids = await trash_repo.fetch_active_folder_ids(db)
            for f in non_roots:
                if f.parent_id in active_ids:
                    targets.append(f)

        purged_folders_count = 0
        for folder in targets:
            try:
                purged_f, purged_p = await TrashService.purge_folder_subtree(db, folder.id)
                await db.commit()
                purged_folders_count += purged_f
                deleted_photos_count += purged_p
            except Exception as exc:
                await db.rollback()
                logger.warning(
                    "photos.cleanup.folder_failed",
                    folder_id=str(folder.id),
                    error=str(exc),
                )
        return {"purged_photos": deleted_photos_count, "purged_folders": purged_folders_count}

    @staticmethod
    async def empty_trash(db: AsyncSession) -> dict[str, int]:
        """Окончательно удаляет ВСЕ элементы из корзины (фото и папки) без учета TTL.

        Orchestrator: коммитит per-iteration аналогично ``purge_expired``.
        """
        photos = await trash_repo.fetch_all_trashed_photos(db)
        deleted_photos_count = await TrashService._purge_photo_rows(db, photos)
        await db.commit()

        folders = list(await trash_repo.fetch_all_trashed_folders(db))
        trash_ids = {f.id for f in folders}
        roots = [f for f in folders if f.parent_id not in trash_ids]

        purged_folders_count = 0
        for folder in roots:
            try:
                purged_f, purged_p = await TrashService.purge_folder_subtree(db, folder.id)
                await db.commit()
                purged_folders_count += purged_f
                deleted_photos_count += purged_p
            except Exception as exc:
                await db.rollback()
                logger.warning(
                    "photos.cleanup.folder_failed",
                    folder_id=str(folder.id),
                    error=str(exc),
                )
        return {"purged_photos": deleted_photos_count, "purged_folders": purged_folders_count}

    @staticmethod
    async def list_trashed_folders(db: AsyncSession) -> list[PhotoFolder]:
        return list(await folder_repo.fetch_deleted_folders_ordered(db))

    @staticmethod
    async def empty_trash_for_user(db: AsyncSession, user: User, redis: Redis) -> dict[str, int]:
        """Окончательно удаляет элементы корзины, доступные пользователю (manager).

        Orchestrator: коммитит per-item / per-folder.
        """
        deleted_photos_count = 0

        all_rows = await photo_repo.fetch_deleted_photos_with_folders(
            db, datetime.now(UTC) + timedelta(days=1)
        )
        unique_folders: dict[uuid.UUID, PhotoFolder] = {}
        for _photo, folder in all_rows:
            if folder is not None and folder.id not in unique_folders:
                unique_folders[folder.id] = folder
        folder_perm_cache = await resolve_folders_permissions_batch(
            user, list(unique_folders.values()), db, redis
        )

        for photo, folder in all_rows:
            if folder is None:
                continue
            perm = folder_perm_cache.get(folder.id)
            if not perm_gte(perm, PERM_MANAGER):
                continue
            try:
                await TrashService.purge_photo(db, photo.id)
                await db.commit()
                deleted_photos_count += 1
            except Exception as exc:
                await db.rollback()
                logger.warning(
                    "photos.trash.user_empty.photo_failed",
                    photo_id=str(photo.id),
                    user_id=str(user.id),
                    error=str(exc),
                )

        folders = list(await folder_repo.fetch_deleted_folders_ordered(db))
        folder_perms_batch = await resolve_folders_permissions_batch(user, folders, db, redis)
        accessible_ids: set[uuid.UUID] = {
            f.id for f in folders if perm_gte(folder_perms_batch.get(f.id), PERM_MANAGER)
        }

        roots = [f for f in folders if f.id in accessible_ids and f.parent_id not in accessible_ids]

        purged_folders_count = 0
        for folder in roots:
            try:
                purged_f, purged_p = await TrashService.purge_folder_subtree(db, folder.id)
                await db.commit()
                purged_folders_count += purged_f
                deleted_photos_count += purged_p
            except Exception as exc:
                await db.rollback()
                logger.warning(
                    "photos.trash.user_empty.folder_failed",
                    folder_id=str(folder.id),
                    user_id=str(user.id),
                    error=str(exc),
                )

        logger.info(
            "photos.trash.user_emptied",
            user_id=str(user.id),
            purged_photos=deleted_photos_count,
            purged_folders=purged_folders_count,
        )
        return {
            "purged_photos": deleted_photos_count,
            "purged_folders": purged_folders_count,
        }

    @staticmethod
    async def list_trashed_photos(
        db: AsyncSession, user: User, redis: Redis, *, page: int, per_page: int
    ) -> PhotoList:
        cutoff = datetime.now(UTC) - timedelta(days=30)
        offset = (page - 1) * per_page

        if user.role == "admin":
            total = await photo_repo.count_deleted_photos_admin(db, cutoff)
            rows = await photo_repo.fetch_deleted_photos_admin_page(
                db, cutoff, offset=offset, limit=per_page
            )
            items = [photo_to_public(photo, folder) for photo, folder in rows]
            return PhotoList(items=items, total=total, page=page, per_page=per_page)

        all_rows = await photo_repo.fetch_deleted_photos_with_folders(db, cutoff)

        unique_folders: dict[uuid.UUID, PhotoFolder] = {}
        for _photo, folder in all_rows:
            if folder is not None and folder.id not in unique_folders:
                unique_folders[folder.id] = folder

        folder_perm_cache = await resolve_folders_permissions_batch(
            user, list(unique_folders.values()), db, redis
        )

        accessible_items: list[PhotoPublic] = []
        for photo, folder in all_rows:
            if folder is None:
                continue
            perm = folder_perm_cache.get(folder.id)
            if not perm_gte(perm, PERM_MANAGER):
                continue
            accessible_items.append(photo_to_public(photo, folder))

        total = len(accessible_items)
        items = accessible_items[offset : offset + per_page]
        return PhotoList(items=items, total=total, page=page, per_page=per_page)


__all__ = ["TrashService"]
