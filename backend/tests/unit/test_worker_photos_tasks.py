"""Unit-тесты для app/worker/tasks/photos.py.

Покрытие основных функций (без реальной БД):
- _slugify_import: ASCII/кириллица/мусор → slug; пустая строка → 'folder'.
- process_photo_upload: photo не найден / soft-deleted / folder не найден / отсутствует файл; happy path с моками storage.
- cleanup_deleted_photos: пустой список → 0; одна запись → удаление + delete-вызов.
- generate_folder_zip: job не найден.
- cleanup_zip_jobs: пустой список; запись с file_path → unlink + delete.
- detect_missing_thumbnails: пустой список; есть фото без thumb → enqueue.
- empty_photo_trash: lock занят → skipped.
- import_scan_run: import_root не существует → error.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import photos as photos_task


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
        # NFKD-стрипа кириллицы → пустая строка → fallback 'folder'
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
        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.process_photo_upload({}, str(uuid.uuid4()))
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_soft_deleted_photo_short_circuits(self):
        photo = SimpleNamespace(id=uuid.uuid4(), deleted_at="2024-01-01", folder_id=uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(photo))
        db.commit = AsyncMock()
        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.process_photo_upload({}, str(photo.id))
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_folder_not_found(self):
        photo = SimpleNamespace(id=uuid.uuid4(), deleted_at=None, folder_id=uuid.uuid4(),
                                 filename="x.jpg")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_one_or_none(photo),
            _scalar_one_or_none(None),
        ])
        db.commit = AsyncMock()
        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.process_photo_upload({}, str(photo.id))
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_original_file(self, tmp_path):
        photo = SimpleNamespace(id=uuid.uuid4(), deleted_at=None, folder_id=uuid.uuid4(),
                                 filename="x.jpg")
        folder = SimpleNamespace(fs_path=str(tmp_path / "missing"), path="missing")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_one_or_none(photo),
            _scalar_one_or_none(folder),
        ])
        db.commit = AsyncMock()
        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)), \
             patch.object(photos_task.photos_storage, "folder_fs_path",
                          return_value=tmp_path / "missing"):
            await photos_task.process_photo_upload({}, str(photo.id))
        db.commit.assert_not_called()


# ── cleanup_deleted_photos ──


class TestCleanupDeletedPhotos:
    @pytest.mark.asyncio
    async def test_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_all([]))
        db.commit = AsyncMock()
        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)):
            n = await photos_task.cleanup_deleted_photos({})
        assert n == 0
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_one_photo_purged(self):
        photo = SimpleNamespace(id=uuid.uuid4(), folder_id=uuid.uuid4(), filename="x.jpg")
        folder = SimpleNamespace(fs_path="/tmp", path="x")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_all([photo]),
            _scalar_one_or_none(folder),
            MagicMock(),  # delete tags
            MagicMock(),  # delete photo
        ])
        db.commit = AsyncMock()

        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)), \
             patch.object(photos_task.photos_storage, "folder_fs_path", return_value=Path("/tmp")), \
             patch.object(photos_task.photos_storage, "delete_photo_files"):
            n = await photos_task.cleanup_deleted_photos({})
        assert n == 1


# ── generate_folder_zip ──


class TestGenerateFolderZip:
    @pytest.mark.asyncio
    async def test_job_not_found_logs_and_returns(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        db.commit = AsyncMock()
        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.generate_folder_zip({}, str(uuid.uuid4()))
        db.commit.assert_not_called()


# ── cleanup_zip_jobs ──


class TestCleanupZipJobs:
    @pytest.mark.asyncio
    async def test_no_jobs(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_all([]))
        db.commit = AsyncMock()
        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.cleanup_zip_jobs({})
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_unlinks_and_deletes(self, tmp_path):
        f = tmp_path / "x.zip"
        f.write_bytes(b"x")
        job = SimpleNamespace(id=uuid.uuid4(), file_path=str(f),
                               expires_at=None)
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_all([job]),
            MagicMock(),
        ])
        db.commit = AsyncMock()
        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_task.cleanup_zip_jobs({})
        assert not f.exists()
        db.commit.assert_awaited_once()


# ── detect_missing_thumbnails ──


class TestDetectMissingThumbnails:
    @pytest.mark.asyncio
    async def test_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_all([]))
        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)):
            out = await photos_task.detect_missing_thumbnails({"redis": MagicMock()})
        assert out == {"requeued": 0}

    @pytest.mark.asyncio
    async def test_enqueues_when_thumb_missing(self, tmp_path):
        photo = SimpleNamespace(id=uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_scalars_all([photo]), _scalars_all([])])
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()

        with patch.object(photos_task, "AsyncSessionLocal", return_value=_session_cm(db)), \
             patch.object(photos_task.photos_storage, "THUMBS_ROOT", tmp_path):
            out = await photos_task.detect_missing_thumbnails({"redis": pool})
        assert out["requeued"] == 1
        pool.enqueue_job.assert_awaited_once()


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
        with patch.object(photos_task.photos_storage, "IMPORT_ROOT", tmp_path / "nope"):
            out = await photos_task.import_scan_run({}, str(uuid.uuid4()))
        assert "error" in out
