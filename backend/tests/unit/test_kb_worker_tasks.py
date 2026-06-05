from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import app.worker.tasks.kb as kb_task


def _session_cm(db):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


class TestPurgeKbTrash:
    async def test_disabled_when_retention_le_zero(self):
        with (
            patch.object(
                kb_task,
                "load_system_settings",
                return_value=SimpleNamespace(kb_trash_retention_days=0),
            ),
            patch.object(kb_task, "purge_expired_articles", new=AsyncMock()) as purge,
        ):
            result = await kb_task.purge_kb_trash({})

        assert result == 0
        purge.assert_not_awaited()

    async def test_purges_when_retention_positive(self):
        db = MagicMock()
        with (
            patch.object(
                kb_task,
                "load_system_settings",
                return_value=SimpleNamespace(kb_trash_retention_days=30),
            ),
            patch.object(kb_task, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(
                kb_task, "purge_expired_articles", new=AsyncMock(return_value=7)
            ) as purge,
        ):
            result = await kb_task.purge_kb_trash({})

        assert result == 7
        purge.assert_awaited_once_with(db, 30)


class TestCleanupOrphanDirs:
    async def test_returns_removed_count(self):
        db = MagicMock()
        with (
            patch.object(kb_task, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(
                kb_task, "cleanup_orphan_dirs", new=AsyncMock(return_value=3)
            ) as cleanup,
        ):
            result = await kb_task.cleanup_kb_orphan_dirs({})

        assert result == 3
        cleanup.assert_awaited_once_with(db)
