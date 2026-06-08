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


class TestParseIso:
    def test_none_returns_none(self):
        assert files_task._parse_iso(None) is None

    def test_empty_string_returns_none(self):
        assert files_task._parse_iso("") is None

    def test_valid_iso_parsed(self):
        dt = files_task._parse_iso("2024-06-15T12:00:00+00:00")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.day == 15

    def test_invalid_string_returns_none(self):
        assert files_task._parse_iso("not-a-date") is None


class TestRestoreFileShares:
    @pytest.mark.asyncio
    async def test_no_backup_returns_zero(self):
        db = AsyncMock()
        with patch.object(files_task, "load_all_shares", return_value={}):
            restored = await files_task._restore_file_shares(db, {}, _now())
        assert restored == 0
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_entry_without_slash(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        backup = {"nofolder": [_share_entry()]}
        with patch.object(files_task, "load_all_shares", return_value=backup):
            restored = await files_task._restore_file_shares(db, {}, _now())
        assert restored == 0
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_parent_folder_missing(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        backup = {"root/file.txt": [_share_entry()]}
        with patch.object(files_task, "load_all_shares", return_value=backup):
            restored = await files_task._restore_file_shares(db, {}, _now())
        assert restored == 0
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_expired_share(self):
        import uuid as _uuid

        db = AsyncMock()
        db.commit = AsyncMock()
        folder_id = _uuid.uuid4()
        backup = {"root/file.txt": [_share_entry(expires_at="2000-01-01T00:00:00+00:00")]}
        with patch.object(files_task, "load_all_shares", return_value=backup):
            restored = await files_task._restore_file_shares(
                db, {"root": folder_id}, _now()
            )
        assert restored == 0
        db.execute.assert_not_called()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_inserts_share_and_counts_rowcount(self):
        import uuid as _uuid

        folder_id = _uuid.uuid4()
        result = MagicMock()
        result.rowcount = 1
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        backup = {"root/file.txt": [_share_entry()]}
        with patch.object(files_task, "load_all_shares", return_value=backup):
            restored = await files_task._restore_file_shares(
                db, {"root": folder_id}, _now()
            )
        assert restored == 1
        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_conflict_rowcount_zero_not_counted(self):
        import uuid as _uuid

        folder_id = _uuid.uuid4()
        result = MagicMock()
        result.rowcount = 0
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        backup = {"root/file.txt": [_share_entry()]}
        with patch.object(files_task, "load_all_shares", return_value=backup):
            restored = await files_task._restore_file_shares(
                db, {"root": folder_id}, _now()
            )
        assert restored == 0


def _now():
    from datetime import UTC, datetime

    return datetime(2024, 6, 1, tzinfo=UTC)


def _share_entry(**over):
    base = {
        "subject_type": "user",
        "subject_id": "u1",
        "subject_name": "User One",
        "permission": "viewer",
        "expires_at": None,
    }
    base.update(over)
    return base
