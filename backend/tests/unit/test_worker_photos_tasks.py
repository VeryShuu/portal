"""Unit-тесты для app/worker/tasks/photos/* (пакет после декомпозиции)."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import photos as photos_task
from app.worker.tasks.photos import cleanup as photos_cleanup
from app.worker.tasks.photos import import_scan as photos_import_scan
from app.worker.tasks.photos import processing as photos_processing
from app.worker.tasks.photos import zip_jobs as photos_zip_jobs


def _session_cm(db: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _scalar_one_or_none(value):
    res = MagicMock()
    res.scalar_one_or_none.return_value = value
    return res


def _scalars_all(values):
    res = MagicMock()
    inner = MagicMock()
    inner.all.return_value = values
    res.scalars.return_value = inner
    return res


# ── _slugify_import ──


class TestSlugifyImport:
    def test_ascii_lowercased_and_dashed(self):
        assert photos_task._slugify_import("Hello World") == "hello-world"

    def test_cyrillic_to_ascii_or_default(self):
        out = photos_task._slugify_import("Привет Мир")
        assert out == "folder"

    def test_special_chars_stripped(self):
        assert photos_task._slugify_import("a/b\\c?d") == "abcd"

    def test_empty_returns_default(self):
        assert photos_task._slugify_import("") == "folder"

    def test_collapses_separators(self):
        assert photos_task._slugify_import("foo___bar  baz") == "foo-bar-baz"


# ── process_photo_upload ──


class TestProcessPhotoUpload:
    @pytest.mark.asyncio
    async def test_photo_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        db.commit = AsyncMock()
        with patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.process_photo_upload({}, str(uuid.uuid4()))
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_soft_deleted_photo_short_circuits(self):
        photo = SimpleNamespace(id=uuid.uuid4(), deleted_at="2024-01-01", folder_id=uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(photo))
        db.commit = AsyncMock()
        with patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.process_photo_upload({}, str(photo.id))
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_folder_not_found(self):
        photo = SimpleNamespace(
            id=uuid.uuid4(), deleted_at=None, folder_id=uuid.uuid4(), filename="x.jpg"
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(photo),
                _scalar_one_or_none(None),
            ]
        )
        db.commit = AsyncMock()
        with patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.process_photo_upload({}, str(photo.id))
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_original_file(self, tmp_path):
        photo = SimpleNamespace(
            id=uuid.uuid4(), deleted_at=None, folder_id=uuid.uuid4(), filename="x.jpg"
        )
        folder = SimpleNamespace(fs_path=str(tmp_path / "missing"), path="missing")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(photo),
                _scalar_one_or_none(folder),
            ]
        )
        db.commit = AsyncMock()
        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(
                photos_processing.photos_storage,
                "folder_fs_path",
                return_value=tmp_path / "missing",
            ),
        ):
            await photos_task.process_photo_upload({}, str(photo.id))
        db.commit.assert_not_called()


# ── cleanup_deleted_photos ──


class TestCleanupDeletedPhotos:
    @pytest.mark.asyncio
    async def test_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_all([]))
        db.commit = AsyncMock()
        with patch.object(photos_cleanup, "AsyncSessionLocal", return_value=_session_cm(db)):
            n = await photos_task.cleanup_deleted_photos({})
        assert n == 0
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_one_photo_purged(self):
        from app.services.photos_trash import TrashService

        db = AsyncMock()
        with (
            patch.object(photos_cleanup, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(
                TrashService,
                "purge_expired",
                return_value={"purged_photos": 1, "purged_folders": 0},
            ) as mock_purge,
        ):
            n = await photos_task.cleanup_deleted_photos({})
        assert n == 1
        mock_purge.assert_called_once_with(db, ttl_days=30)

    @pytest.mark.asyncio
    async def test_ttl_days_boundary_is_30(self):
        """#B-8: TTL для cleanup_deleted_photos зафиксирован на 30 днях."""
        from app.services.photos_trash import TrashService

        db = AsyncMock()
        with (
            patch.object(photos_cleanup, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(
                TrashService,
                "purge_expired",
                return_value={"purged_photos": 7, "purged_folders": 2},
            ) as mock_purge,
        ):
            n = await photos_task.cleanup_deleted_photos({})
        assert n == 7
        _args, kwargs = mock_purge.call_args
        assert kwargs.get("ttl_days") == 30


# ── generate_folder_zip ──


class TestGenerateFolderZip:
    @pytest.mark.asyncio
    async def test_job_not_found_logs_and_returns(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        db.commit = AsyncMock()
        with patch.object(photos_zip_jobs, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.generate_folder_zip({}, str(uuid.uuid4()))
        db.commit.assert_not_called()


# ── cleanup_zip_jobs ──


class TestCleanupZipJobs:
    @pytest.mark.asyncio
    async def test_no_jobs(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_all([]))
        db.commit = AsyncMock()
        with patch.object(photos_cleanup, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.cleanup_zip_jobs({})
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_unlinks_and_deletes(self, tmp_path):
        f = tmp_path / "x.zip"
        f.write_bytes(b"x")
        job = SimpleNamespace(id=uuid.uuid4(), file_path=str(f), expires_at=None)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([job]),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()
        with patch.object(photos_cleanup, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.cleanup_zip_jobs({})
        assert not f.exists()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_file_does_not_raise(self, tmp_path):
        """#B-8: TTL-boundary — exires_at в прошлом, файла уже нет на диске → не падает."""
        job = SimpleNamespace(
            id=uuid.uuid4(),
            file_path=str(tmp_path / "gone.zip"),
            expires_at=None,
        )
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_scalars_all([job]), MagicMock()])
        db.commit = AsyncMock()
        with patch.object(photos_cleanup, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.cleanup_zip_jobs({})
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_filter_uses_expires_at_cutoff(self):
        """#B-8: SQL-фильтр выбирает только записи с expires_at < now (TTL-граница)."""
        captured = []

        async def fake_execute(stmt, *args, **kwargs):
            captured.append(str(stmt.compile(compile_kwargs={"literal_binds": False})))
            return _scalars_all([])

        db = AsyncMock()
        db.execute = fake_execute
        db.commit = AsyncMock()
        with patch.object(photos_cleanup, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.cleanup_zip_jobs({})
        assert captured, "cleanup_zip_jobs must issue at least a SELECT"
        assert "expires_at" in captured[0].lower()


# ── detect_missing_thumbnails ──


class TestDetectMissingThumbnails:
    @pytest.mark.asyncio
    async def test_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_all([]))
        with patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)):
            out = await photos_task.detect_missing_thumbnails({"redis": MagicMock()})
        assert out == {"requeued": 0}

    @pytest.mark.asyncio
    async def test_enqueues_when_thumb_missing(self, tmp_path):
        photo = SimpleNamespace(id=uuid.uuid4())
        db = AsyncMock()
        db.execute.side_effect = [_scalars_all([photo]), _scalars_all([])]
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_task.detect_missing_thumbnails({"redis": pool})
        assert out["requeued"] == 1
        pool.enqueue_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueues_when_unprocessed_and_old(self, tmp_path):
        photo = SimpleNamespace(id=uuid.uuid4(), processed=False)
        db = AsyncMock()
        db.execute.side_effect = [_scalars_all([photo]), _scalars_all([])]
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_task.detect_missing_thumbnails({"redis": pool})
        assert out["requeued"] == 1
        pool.enqueue_job.assert_awaited_once_with(
            "process_photo_upload",
            str(photo.id),
            _job_id=f"photos:process:{photo.id}",
        )

    @pytest.mark.asyncio
    async def test_skips_when_thumb_present(self, tmp_path):
        """#B-7: свежий thumb на диске → реквью не нужен."""
        photo = SimpleNamespace(id=uuid.uuid4(), processed=True)
        # Pre-create the 200.webp file the cron checks for.
        thumb_dir = tmp_path / str(photo.id)
        thumb_dir.mkdir(parents=True)
        (thumb_dir / "200.webp").write_bytes(b"thumb")

        db = AsyncMock()
        db.execute.side_effect = [_scalars_all([photo]), _scalars_all([])]
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_task.detect_missing_thumbnails({"redis": pool})
        assert out["requeued"] == 0
        pool.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_resets_processed_flag_when_thumb_missing(self, tmp_path):
        """#B-7: рассинхрон БД↔диск — processed=True, но файла нет → флаг сбрасывается."""
        photo = SimpleNamespace(id=uuid.uuid4(), processed=True)
        db = AsyncMock()
        # 1st execute: select photos batch; 2nd: update processed=False; 3rd: empty next page.
        db.execute.side_effect = [
            _scalars_all([photo]),
            MagicMock(),
            _scalars_all([]),
        ]
        db.commit = AsyncMock()
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_task.detect_missing_thumbnails({"redis": pool})
        assert out["requeued"] == 1
        # Reset of processed flag must be committed before enqueue (#B-7 invariant).
        assert db.commit.await_count >= 1
        pool.enqueue_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_redis_pool_short_circuits(self):
        """#B-7: при отсутствии redis-пула задача не падает и не реквьюит ничего."""
        out = await photos_task.detect_missing_thumbnails({})
        assert out == {"requeued": 0}


# ── empty_photo_trash ──


class TestEmptyPhotoTrash:
    @pytest.mark.asyncio
    async def test_skipped_when_lock_held(self):
        redis = MagicMock()
        redis.set = AsyncMock(return_value=False)
        redis.delete = AsyncMock()
        out = await photos_task.empty_photo_trash({"redis": redis}, "uid")
        assert out == {"purged": 0, "skipped": "already_running"}
        redis.delete.assert_not_called()


# ── import_scan_run ──


class TestImportScanRun:
    @pytest.mark.asyncio
    async def test_missing_root_returns_error(self, tmp_path):
        with patch.object(photos_import_scan.photos_storage, "IMPORT_ROOT", tmp_path / "nope"):
            out = await photos_task.import_scan_run({}, str(uuid.uuid4()))
        assert "error" in out

    @pytest.mark.asyncio
    async def test_import_scan_success_moves_files(self, tmp_path):
        import_root = tmp_path / "import"
        import_root.mkdir()
        sub_dir = import_root / "Vacation"
        sub_dir.mkdir()
        img_file = sub_dir / "sunset.jpg"
        img_file.write_bytes(b"image_bytes")

        originals_root = tmp_path / "originals"
        originals_root.mkdir()

        db = AsyncMock()
        db.scalar = AsyncMock(
            side_effect=[
                None,  # count_siblings_with_slug
                None,  # check if sunset.jpg already exists
            ]
        )
        db.scalars = MagicMock()
        db.execute = AsyncMock()

        pool = MagicMock()
        pool.enqueue_job = AsyncMock()

        user_id = str(uuid.uuid4())

        with (
            patch.object(photos_import_scan.photos_storage, "IMPORT_ROOT", import_root),
            patch.object(photos_import_scan.photos_storage, "ORIGINALS_ROOT", originals_root),
            patch.object(photos_import_scan, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch("app.services.photos_folder_repo.fetch_sibling_fs_segments", return_value=set()),
        ):
            out = await photos_task.import_scan_run({"redis": pool}, user_id)

        assert out["folders_created"] == 1
        assert out["photos_imported"] == 1
        assert not img_file.exists()  # Was moved from import directory!
        assert (originals_root / "Vacation" / "sunset.jpg").exists()  # Moved to originals!
        assert (originals_root / "Vacation" / "sunset.jpg").read_bytes() == b"image_bytes"
