"""ARQ задачи модуля файлов (Nextcloud)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.files import FileFolder, FileFolderPermission
from app.services.files_acl_persistence import get_folder_perms
from app.services.nextcloud import NextcloudError, get_nc_service

logger = get_logger(__name__)

_SYNC_LOCK_KEY = "files:startup_sync_lock"
_SYNC_LOCK_TTL = 300
_SYNC_LOCK_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) "
    "else return 0 end"
)


async def startup_sync_nc_folders(ctx: dict) -> None:
    """Фоновый BFS-обход папок Nextcloud при старте worker'а.

    Запускается через cron с run_at_startup=True и задержкой 30 с,
    чтобы дать NC время подняться. Идемпотентна — повторный запуск
    пропускает уже существующие папки. Права восстанавливаются из
    files-acl.json. Для предотвращения параллельного запуска используется
    Redis-блокировка (TTL 5 мин).
    """
    from app.core.modules_config import load_modules

    modules = load_modules()
    if not modules.nextcloud.enabled:
        logger.info("files.startup_sync.skipped", reason="nextcloud_disabled")
        return

    redis = ctx.get("redis")
    lock_token: str | None = None
    if redis is not None:
        lock_token = secrets.token_hex(16)
        acquired = await redis.set(_SYNC_LOCK_KEY, lock_token, nx=True, ex=_SYNC_LOCK_TTL)
        if not acquired:
            logger.info("files.startup_sync.skipped", reason="lock_held")
            return

    try:
        nc = get_nc_service()
        try:
            nc_paths = await nc.list_folders_recursive(max_depth=30)
        except NextcloudError as exc:
            logger.warning("files.startup_sync.nc_error", error=str(exc))
            return

        if not nc_paths:
            logger.info("files.startup_sync.done", created=0, skipped=0)
            return

        now = datetime.now(UTC)
        created = 0
        skipped = 0
        perms_restored = 0

        async with AsyncSessionLocal() as db:
            res = await db.execute(select(FileFolder.nc_path, FileFolder.id))
            path_to_id: dict[str, uuid.UUID] = {row.nc_path: row.id for row in res}

            for nc_path in nc_paths:
                if nc_path in path_to_id:
                    skipped += 1
                    continue

                name = nc_path.rsplit("/", 1)[-1] if "/" in nc_path else nc_path
                parent_nc_path = nc_path.rsplit("/", 1)[0] if "/" in nc_path else None
                parent_id: uuid.UUID | None = (
                    path_to_id.get(parent_nc_path) if parent_nc_path else None
                )

                new_id = uuid.uuid4()
                stmt = (
                    insert(FileFolder)
                    .values(
                        id=new_id,
                        parent_id=parent_id,
                        name=name,
                        nc_path=nc_path,
                        description=None,
                        created_by=None,
                        created_at=now,
                        updated_at=now,
                        deleted_at=None,
                    )
                    .on_conflict_do_nothing(index_elements=["nc_path"])
                )
                result = await db.execute(stmt)
                if result.rowcount:  # type: ignore[attr-defined]
                    path_to_id[nc_path] = new_id
                    created += 1

                    backed_up = get_folder_perms(nc_path)
                    for entry in backed_up:
                        perm_stmt = (
                            insert(FileFolderPermission)
                            .values(
                                id=uuid.uuid4(),
                                folder_id=new_id,
                                subject_type=entry["subject_type"],
                                subject_id=entry["subject_id"],
                                subject_name=entry["subject_name"],
                                permission=entry["permission"],
                                granted_by=None,
                                created_at=now,
                            )
                            .on_conflict_do_nothing()
                        )
                        await db.execute(perm_stmt)
                        perms_restored += 1
                else:
                    skipped += 1

            await db.commit()

        logger.info(
            "files.startup_sync.done",
            created=created,
            skipped=skipped,
            perms_restored=perms_restored,
        )

    finally:
        if redis is not None and lock_token is not None:
            try:
                await redis.eval(_SYNC_LOCK_RELEASE_LUA, 1, _SYNC_LOCK_KEY, lock_token)
            except Exception as exc:
                logger.warning("files.startup_sync.lock_release_failed", error=str(exc))
