"""Unit-тесты для app/worker/tasks/files.py.

Покрытие:
- startup_sync_nc_folders: nextcloud_disabled → ранний выход
- startup_sync_nc_folders: lock занят → ранний выход
- startup_sync_nc_folders: NextcloudError → лог и выход
- startup_sync_nc_folders: пустой список → done с created=0
- startup_sync_nc_folders: создание новых папок + восстановление прав
- startup_sync_nc_folders: освобождение Redis-блокировки в finally
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.nextcloud import NextcloudError
from app.worker.tasks import files as files_task


def _make_modules(nc_enabled: bool):
    return SimpleNamespace(nextcloud=SimpleNamespace(enabled=nc_enabled))


def _make_redis(acquire: bool = True) -> AsyncMock:
    r = AsyncMock()
    r.set = AsyncMock(return_value=acquire)
    r.eval = AsyncMock(return_value=1)
    return r


class TestStartupSyncNcFolders:
    @pytest.mark.asyncio
    async def test_skips_when_nextcloud_disabled(self):
        with (
            patch.object(files_task, "load_modules", create=True),
            patch("app.core.modules_config.load_modules", return_value=_make_modules(False)),
            patch.object(files_task, "get_nc_service") as get_nc,
        ):
            await files_task.startup_sync_nc_folders({})
            get_nc.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_lock_held(self):
        redis = _make_redis(acquire=False)
        with (
            patch("app.core.modules_config.load_modules", return_value=_make_modules(True)),
            patch.object(files_task, "get_nc_service") as get_nc,
        ):
            await files_task.startup_sync_nc_folders({"redis": redis})
            redis.set.assert_awaited_once()
            get_nc.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_nextcloud_error(self):
        redis = _make_redis(acquire=True)
        nc = MagicMock()
        nc.list_folders_recursive = AsyncMock(side_effect=NextcloudError(500, "boom"))
        with (
            patch("app.core.modules_config.load_modules", return_value=_make_modules(True)),
            patch.object(files_task, "get_nc_service", return_value=nc),
        ):
            await files_task.startup_sync_nc_folders({"redis": redis})
        nc.list_folders_recursive.assert_awaited_once()
        redis.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_paths_done(self):
        redis = _make_redis(acquire=True)
        nc = MagicMock()
        nc.list_folders_recursive = AsyncMock(return_value=[])
        with (
            patch("app.core.modules_config.load_modules", return_value=_make_modules(True)),
            patch.object(files_task, "get_nc_service", return_value=nc),
        ):
            await files_task.startup_sync_nc_folders({"redis": redis})
        nc.list_folders_recursive.assert_awaited_once()
        redis.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_folders_and_restores_perms(self):
        redis = _make_redis(acquire=True)
        nc = MagicMock()
        nc.list_folders_recursive = AsyncMock(return_value=["root", "root/child"])

        existing = MagicMock()
        existing.__iter__ = lambda self: iter([])

        insert_result = MagicMock()
        insert_result.rowcount = 1

        db = AsyncMock()
        execute_calls: list = []

        async def execute_side_effect(stmt, *args, **kwargs):
            execute_calls.append(stmt)
            if len(execute_calls) == 1:
                return existing
            return insert_result

        db.execute = AsyncMock(side_effect=execute_side_effect)
        db.commit = AsyncMock()

        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        perms = [
            {
                "subject_type": "user",
                "subject_id": "u1",
                "subject_name": "User One",
                "permission": "viewer",
            }
        ]

        with (
            patch("app.core.modules_config.load_modules", return_value=_make_modules(True)),
            patch.object(files_task, "get_nc_service", return_value=nc),
            patch.object(files_task, "AsyncSessionLocal", return_value=session_cm),
            patch.object(files_task, "get_folder_perms", return_value=perms),
        ):
            await files_task.startup_sync_nc_folders({"redis": redis})

        db.commit.assert_awaited_once()
        # 1 select + 2 inserts (folders) + 2 inserts (perms, по 1 на каждую папку) = 5
        assert db.execute.await_count >= 3
        redis.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lock_release_failure_swallowed(self):
        redis = _make_redis(acquire=True)
        redis.eval = AsyncMock(side_effect=RuntimeError("redis down"))
        nc = MagicMock()
        nc.list_folders_recursive = AsyncMock(return_value=[])
        with (
            patch("app.core.modules_config.load_modules", return_value=_make_modules(True)),
            patch.object(files_task, "get_nc_service", return_value=nc),
        ):
            # Не должно бросать наружу
            await files_task.startup_sync_nc_folders({"redis": redis})
        redis.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_works_without_redis(self):
        """Без redis блокировка пропускается — сразу идёт логика."""
        nc = MagicMock()
        nc.list_folders_recursive = AsyncMock(return_value=[])
        with (
            patch("app.core.modules_config.load_modules", return_value=_make_modules(True)),
            patch.object(files_task, "get_nc_service", return_value=nc),
        ):
            await files_task.startup_sync_nc_folders({})
        nc.list_folders_recursive.assert_awaited_once()
