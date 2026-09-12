from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _make_db(rowcount=1, rows=None):
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.rowcount = rowcount
    if rows is not None:
        execute_result.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=execute_result)
    db.commit = AsyncMock()
    return db


class TestRmtree:
    async def test_rmtree_existing_path(self, tmp_path):
        from app.services.kb_trash import _rmtree

        target = tmp_path / "subdir"
        target.mkdir()
        (target / "file.txt").write_text("hello")

        await _rmtree(target)
        assert not target.exists()

    async def test_rmtree_nonexistent_is_noop(self, tmp_path):
        from app.services.kb_trash import _rmtree

        path = tmp_path / "does_not_exist"
        await _rmtree(path)

    async def test_rmtree_exception_logged(self, tmp_path):
        from app.services.kb_trash import _rmtree

        path = tmp_path / "some_dir"
        path.mkdir()

        with patch("asyncio.to_thread", side_effect=RuntimeError("boom")):
            await _rmtree(path)


class TestRemoveArticleDirs:
    async def test_calls_rmtree_on_both_roots(self, tmp_path):
        from app.services import kb_trash as kbt

        files_root = tmp_path / "files"
        media_root = tmp_path / "media"
        files_root.mkdir()
        media_root.mkdir()

        aid = uuid.uuid4()
        (files_root / str(aid)).mkdir()
        (media_root / str(aid)).mkdir()

        with (
            patch.object(kbt, "_kb_files_root", return_value=files_root),
            patch.object(kbt, "_kb_media_root", return_value=media_root),
        ):
            await kbt.remove_article_dirs(aid)

        assert not (files_root / str(aid)).exists()
        assert not (media_root / str(aid)).exists()

    async def test_remove_nonexistent_is_safe(self, tmp_path):
        from app.services import kb_trash as kbt

        files_root = tmp_path / "files"
        media_root = tmp_path / "media"
        files_root.mkdir()
        media_root.mkdir()

        with (
            patch.object(kbt, "_kb_files_root", return_value=files_root),
            patch.object(kbt, "_kb_media_root", return_value=media_root),
        ):
            await kbt.remove_article_dirs(uuid.uuid4())


class TestTryRemoveEmptyArticleDir:
    async def test_removes_empty_files_dir(self, tmp_path):
        from app.services import kb_trash as kbt

        root = tmp_path / "files"
        root.mkdir()
        aid = uuid.uuid4()
        target = root / str(aid)
        target.mkdir()

        with patch.object(kbt, "_kb_files_root", return_value=root):
            await kbt.try_remove_empty_article_dir(aid, "files")
        assert not target.exists()

    async def test_removes_empty_media_dir(self, tmp_path):
        from app.services import kb_trash as kbt

        root = tmp_path / "media"
        root.mkdir()
        aid = uuid.uuid4()
        target = root / str(aid)
        target.mkdir()

        with patch.object(kbt, "_kb_media_root", return_value=root):
            await kbt.try_remove_empty_article_dir(aid, "media")
        assert not target.exists()

    async def test_nonempty_dir_kept(self, tmp_path):
        from app.services import kb_trash as kbt

        root = tmp_path / "files"
        root.mkdir()
        aid = uuid.uuid4()
        target = root / str(aid)
        target.mkdir()
        (target / "file.txt").write_text("x")

        with patch.object(kbt, "_kb_files_root", return_value=root):
            await kbt.try_remove_empty_article_dir(aid, "files")
        assert target.exists()

    async def test_missing_dir_is_noop(self, tmp_path):
        from app.services import kb_trash as kbt

        root = tmp_path / "files"
        root.mkdir()

        with patch.object(kbt, "_kb_files_root", return_value=root):
            await kbt.try_remove_empty_article_dir(uuid.uuid4(), "files")

    async def test_other_exception_logged(self, tmp_path):
        from app.services import kb_trash as kbt

        root = tmp_path / "files"
        root.mkdir()
        aid = uuid.uuid4()
        target = root / str(aid)
        target.mkdir()

        with (
            patch.object(kbt, "_kb_files_root", return_value=root),
            patch("asyncio.to_thread", side_effect=ValueError("unexpected")),
        ):
            await kbt.try_remove_empty_article_dir(aid, "files")


class TestPurgeArticle:
    async def test_purge_existing_returns_true(self, tmp_path):
        from app.services import kb_trash as kbt

        aid = uuid.uuid4()
        db = _make_db(rowcount=1)

        with patch.object(kbt, "remove_article_dirs", AsyncMock()) as mock_rm:
            result = await kbt.purge_article(db, aid)

        assert result is True
        mock_rm.assert_awaited_once_with(aid)
        db.commit.assert_awaited_once()

    async def test_purge_missing_returns_false(self):
        from app.services import kb_trash as kbt

        db = _make_db(rowcount=0)

        with patch.object(kbt, "remove_article_dirs", AsyncMock()) as mock_rm:
            result = await kbt.purge_article(db, uuid.uuid4())

        assert result is False
        mock_rm.assert_not_awaited()


class TestPurgeIdsBatched:
    async def test_empty_list_returns_zero(self):
        from app.services.kb_trash import _purge_ids_batched

        db = _make_db()
        result = await _purge_ids_batched(db, [])
        assert result == 0

    async def test_single_batch(self):
        from app.services import kb_trash as kbt

        ids = [uuid.uuid4() for _ in range(3)]
        db = _make_db(rowcount=3)

        with patch.object(kbt, "_parallel_remove_dirs", AsyncMock()) as mock_prd:
            result = await kbt._purge_ids_batched(db, ids)

        assert result == 3
        mock_prd.assert_awaited_once()

    async def test_multi_batch(self, monkeypatch):
        from app.services import kb_trash as kbt

        monkeypatch.setattr(kbt, "PURGE_BATCH_SIZE", 2)
        ids = [uuid.uuid4() for _ in range(5)]
        db = _make_db(rowcount=2)

        with patch.object(kbt, "_parallel_remove_dirs", AsyncMock()) as mock_prd:
            result = await kbt._purge_ids_batched(db, ids)

        assert result >= 2
        assert mock_prd.await_count >= 2

    async def test_zero_rowcount_skips_rmtree(self):
        from app.services import kb_trash as kbt

        ids = [uuid.uuid4()]
        db = _make_db(rowcount=0)

        with patch.object(kbt, "_parallel_remove_dirs", AsyncMock()) as mock_prd:
            result = await kbt._purge_ids_batched(db, ids)

        assert result == 0
        mock_prd.assert_not_awaited()


class TestPurgeArticlesBulk:
    async def test_delegates_to_batched(self):
        from app.services import kb_trash as kbt

        ids = [uuid.uuid4(), uuid.uuid4()]

        with patch.object(kbt, "_purge_ids_batched", AsyncMock(return_value=2)) as mock:
            result = await kbt.purge_articles_bulk(None, ids)

        assert result == 2
        mock.assert_awaited_once()


class TestPurgeAllTrash:
    async def test_no_trash_returns_zero(self):
        from app.services.kb_trash import purge_all_trash

        execute_result = MagicMock()
        execute_result.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        result = await purge_all_trash(db)
        assert result == 0

    async def test_purges_all_soft_deleted(self):
        from app.services import kb_trash as kbt

        ids = [uuid.uuid4(), uuid.uuid4()]
        call_count = 0

        async def fake_execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.fetchall.return_value = [(i,) for i in ids]
                result.rowcount = len(ids)
            elif call_count == 2:
                result.rowcount = len(ids)
                result.fetchall.return_value = []
            else:
                result.fetchall.return_value = []
                result.rowcount = 0
            return result

        db = AsyncMock()
        db.execute = fake_execute
        db.commit = AsyncMock()

        with patch.object(kbt, "_parallel_remove_dirs", AsyncMock()):
            result = await kbt.purge_all_trash(db)

        assert result == len(ids)

    async def test_logs_when_purged(self):
        from app.services import kb_trash as kbt

        ids = [uuid.uuid4()]
        call_count = 0

        async def fake_execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.fetchall.return_value = [(i,) for i in ids]
                result.rowcount = 1
            elif call_count == 2:
                result.rowcount = 1
                result.fetchall.return_value = []
            else:
                result.fetchall.return_value = []
                result.rowcount = 0
            return result

        db = AsyncMock()
        db.execute = fake_execute
        db.commit = AsyncMock()

        with patch.object(kbt, "_parallel_remove_dirs", AsyncMock()):
            result = await kbt.purge_all_trash(db)

        assert result == 1


class TestPurgeExpiredArticles:
    async def test_retention_zero_returns_zero(self):
        from app.services.kb_trash import purge_expired_articles

        db = AsyncMock()
        assert await purge_expired_articles(db, 0) == 0
        assert await purge_expired_articles(db, -1) == 0
        db.execute.assert_not_called()

    async def test_no_expired_articles(self):
        from app.services.kb_trash import purge_expired_articles

        execute_result = MagicMock()
        execute_result.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        result = await purge_expired_articles(db, 30)
        assert result == 0

    async def test_purges_expired_articles(self):
        from app.services import kb_trash as kbt

        ids = [uuid.uuid4(), uuid.uuid4()]
        call_count = 0

        async def fake_execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.fetchall.return_value = [(i,) for i in ids]
                result.rowcount = len(ids)
            elif call_count == 2:
                result.rowcount = len(ids)
                result.fetchall.return_value = []
            else:
                result.fetchall.return_value = []
                result.rowcount = 0
            return result

        db = AsyncMock()
        db.execute = fake_execute
        db.commit = AsyncMock()

        with patch.object(kbt, "_parallel_remove_dirs", AsyncMock()):
            result = await kbt.purge_expired_articles(db, 30)

        assert result == len(ids)

    async def test_logs_when_done(self):
        from app.services import kb_trash as kbt

        ids = [uuid.uuid4()]
        call_count = 0

        async def fake_execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.fetchall.return_value = [(i,) for i in ids]
                result.rowcount = 1
            elif call_count == 2:
                result.rowcount = 1
                result.fetchall.return_value = []
            else:
                result.fetchall.return_value = []
                result.rowcount = 0
            return result

        db = AsyncMock()
        db.execute = fake_execute
        db.commit = AsyncMock()

        with patch.object(kbt, "_parallel_remove_dirs", AsyncMock()):
            result = await kbt.purge_expired_articles(db, 7)

        assert result == 1


class TestCleanupOrphanDirs:
    async def test_no_roots_returns_zero(self, tmp_path):
        from app.services import kb_trash as kbt

        execute_result = MagicMock()
        execute_result.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        missing = tmp_path / "absent_files"
        missing2 = tmp_path / "absent_media"

        with (
            patch.object(kbt, "_kb_files_root", return_value=missing),
            patch.object(kbt, "_kb_media_root", return_value=missing2),
        ):
            result = await kbt.cleanup_orphan_dirs(db)

        assert result == 0

    async def test_removes_orphan_uuid_dirs(self, tmp_path):
        from app.services import kb_trash as kbt

        files_root = tmp_path / "files"
        media_root = tmp_path / "media"
        files_root.mkdir()
        media_root.mkdir()

        known_id = uuid.uuid4()
        orphan_id = uuid.uuid4()

        (files_root / str(known_id)).mkdir()
        (files_root / str(orphan_id)).mkdir()
        (media_root / str(orphan_id)).mkdir()

        execute_result = MagicMock()
        execute_result.fetchall.return_value = [(known_id,)]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        with (
            patch.object(kbt, "_kb_files_root", return_value=files_root),
            patch.object(kbt, "_kb_media_root", return_value=media_root),
        ):
            result = await kbt.cleanup_orphan_dirs(db)

        assert result == 2
        assert not (files_root / str(orphan_id)).exists()
        assert not (media_root / str(orphan_id)).exists()
        assert (files_root / str(known_id)).exists()

    async def test_skips_non_uuid_entries(self, tmp_path):
        from app.services import kb_trash as kbt

        files_root = tmp_path / "files"
        media_root = tmp_path / "media"
        files_root.mkdir()
        media_root.mkdir()

        (files_root / "notes").mkdir()
        (files_root / "stray.txt").write_text("x")

        execute_result = MagicMock()
        execute_result.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        with (
            patch.object(kbt, "_kb_files_root", return_value=files_root),
            patch.object(kbt, "_kb_media_root", return_value=media_root),
        ):
            result = await kbt.cleanup_orphan_dirs(db)

        assert result == 0
        assert (files_root / "notes").exists()

    async def test_iterdir_exception_continues(self, tmp_path):
        from app.services import kb_trash as kbt

        files_root = tmp_path / "files"
        media_root = tmp_path / "media"
        files_root.mkdir()
        media_root.mkdir()

        execute_result = MagicMock()
        execute_result.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        with (
            patch.object(kbt, "_kb_files_root", return_value=files_root),
            patch.object(kbt, "_kb_media_root", return_value=media_root),
            patch("asyncio.to_thread", side_effect=PermissionError("no access")),
        ):
            result = await kbt.cleanup_orphan_dirs(db)

        assert result == 0

    async def test_logs_when_orphans_removed(self, tmp_path):
        from app.services import kb_trash as kbt

        files_root = tmp_path / "files"
        media_root = tmp_path / "media"
        files_root.mkdir()
        media_root.mkdir()

        orphan_id = uuid.uuid4()
        (files_root / str(orphan_id)).mkdir()

        execute_result = MagicMock()
        execute_result.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        with (
            patch.object(kbt, "_kb_files_root", return_value=files_root),
            patch.object(kbt, "_kb_media_root", return_value=media_root),
        ):
            result = await kbt.cleanup_orphan_dirs(db)

        assert result == 1


class TestParallelRemoveDirs:
    async def test_empty_list_is_noop(self):
        from app.services.kb_trash import _parallel_remove_dirs

        await _parallel_remove_dirs([])

    async def test_calls_remove_for_each(self):
        from app.services import kb_trash as kbt

        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        calls = []

        async def fake_remove(aid):
            calls.append(aid)

        with patch.object(kbt, "remove_article_dirs", fake_remove):
            await kbt._parallel_remove_dirs(ids)

        assert sorted(str(c) for c in calls) == sorted(str(i) for i in ids)
