from __future__ import annotations

import uuid
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def _fetchall(rows):
    res = MagicMock()
    res.fetchall.return_value = rows
    return res


class TestGenerateFolderZip:
    @pytest.mark.asyncio
    async def test_job_not_found_returns_early(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        db.commit = AsyncMock()
        with patch.object(photos_zip_jobs, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_zip_jobs.generate_folder_zip({}, str(uuid.uuid4()))
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_folders_marks_error(self):
        folder_id = uuid.uuid4()
        job = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=folder_id,
            user_id=None,
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(job),
                MagicMock(),
                _fetchall([]),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        with patch.object(photos_zip_jobs, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_zip_jobs.generate_folder_zip({}, str(job.id))

        calls_str = str(db.execute.call_args_list)
        assert db.commit.await_count >= 1

    @pytest.mark.asyncio
    async def test_success_creates_zip_and_marks_done(self, tmp_path):
        folder_id = uuid.uuid4()
        job = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=folder_id,
            user_id=None,
        )

        folder_row = MagicMock()
        folder_row.id = folder_id
        folder_row.parent_id = None
        folder_row.name = "MyFolder"
        folder_row.fs_path = str(tmp_path / "MyFolder")
        folder_row.path = "MyFolder"

        photo = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=folder_id,
            filename="photo.jpg",
            deleted_at=None,
        )

        photo_file = tmp_path / "MyFolder" / "photo.jpg"
        photo_file.parent.mkdir(parents=True, exist_ok=True)
        photo_file.write_bytes(b"jpeg_data")

        zip_root = tmp_path / "zips"
        zip_root.mkdir()

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(job),
                MagicMock(),
                _fetchall([folder_row]),
                _scalars_all([photo]),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        with (
            patch.object(photos_zip_jobs, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_zip_jobs.photos_storage, "ZIPS_ROOT", zip_root),
            patch.object(
                photos_zip_jobs.photos_storage,
                "folder_fs_path",
                return_value=tmp_path / "MyFolder",
            ),
        ):
            await photos_zip_jobs.generate_folder_zip({}, str(job.id))

        assert db.commit.await_count >= 2
        zip_files = list(zip_root.glob("*.zip"))
        assert len(zip_files) == 1

    @pytest.mark.asyncio
    async def test_success_with_nested_folders(self, tmp_path):
        root_folder_id = uuid.uuid4()
        child_folder_id = uuid.uuid4()
        job = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=root_folder_id,
            user_id=uuid.uuid4(),
        )

        root_row = MagicMock()
        root_row.id = root_folder_id
        root_row.parent_id = None
        root_row.name = "Root"
        root_row.fs_path = str(tmp_path / "Root")
        root_row.path = "Root"

        child_row = MagicMock()
        child_row.id = child_folder_id
        child_row.parent_id = root_folder_id
        child_row.name = "SubFolder"
        child_row.fs_path = str(tmp_path / "Root" / "SubFolder")
        child_row.path = "Root/SubFolder"

        photo = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=child_folder_id,
            filename="nested.jpg",
            deleted_at=None,
        )

        photo_file = tmp_path / "Root" / "SubFolder" / "nested.jpg"
        photo_file.parent.mkdir(parents=True, exist_ok=True)
        photo_file.write_bytes(b"data")

        zip_root = tmp_path / "zips"
        zip_root.mkdir()

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(job),
                MagicMock(),
                _fetchall([root_row, child_row]),
                _scalars_all([photo]),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        def fake_folder_fs_path(path_str):
            return tmp_path / path_str.lstrip("/").replace(str(tmp_path) + "/", "")

        with (
            patch.object(photos_zip_jobs, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_zip_jobs.photos_storage, "ZIPS_ROOT", zip_root),
            patch.object(
                photos_zip_jobs.photos_storage,
                "folder_fs_path",
                side_effect=lambda p: (
                    tmp_path / "Root" / "SubFolder" if "SubFolder" in p else tmp_path / "Root"
                ),
            ),
            patch.object(
                photos_zip_jobs.photos_storage,
                "sanitize_filename",
                side_effect=lambda s: s,
            ),
        ):
            await photos_zip_jobs.generate_folder_zip({}, str(job.id))

        zip_files = list(zip_root.glob("*.zip"))
        assert len(zip_files) == 1

    @pytest.mark.asyncio
    async def test_missing_photo_file_is_skipped(self, tmp_path):
        folder_id = uuid.uuid4()
        job = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=folder_id,
            user_id=None,
        )

        folder_row = MagicMock()
        folder_row.id = folder_id
        folder_row.parent_id = None
        folder_row.name = "Folder"
        folder_row.fs_path = str(tmp_path / "Folder")
        folder_row.path = "Folder"

        photo = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=folder_id,
            filename="missing.jpg",
            deleted_at=None,
        )

        zip_root = tmp_path / "zips"
        zip_root.mkdir()
        (tmp_path / "Folder").mkdir(parents=True, exist_ok=True)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(job),
                MagicMock(),
                _fetchall([folder_row]),
                _scalars_all([photo]),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        with (
            patch.object(photos_zip_jobs, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_zip_jobs.photos_storage, "ZIPS_ROOT", zip_root),
            patch.object(
                photos_zip_jobs.photos_storage,
                "folder_fs_path",
                return_value=tmp_path / "Folder",
            ),
        ):
            await photos_zip_jobs.generate_folder_zip({}, str(job.id))

        zip_files = list(zip_root.glob("*.zip"))
        assert len(zip_files) == 1
        with zipfile.ZipFile(zip_files[0]) as zf:
            assert len(zf.namelist()) == 0

    @pytest.mark.asyncio
    async def test_exception_marks_error_status(self):
        folder_id = uuid.uuid4()
        job = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=folder_id,
            user_id=None,
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(job),
                MagicMock(),
                Exception("db crashed"),
            ]
        )
        db.commit = AsyncMock(side_effect=[None, None])

        with patch.object(photos_zip_jobs, "AsyncSessionLocal", return_value=_session_cm(db)):
            await photos_zip_jobs.generate_folder_zip({}, str(job.id))

        assert db.commit.await_count >= 1

    @pytest.mark.asyncio
    async def test_photo_without_folder_in_map_is_skipped(self, tmp_path):
        folder_id = uuid.uuid4()
        other_folder_id = uuid.uuid4()
        job = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=folder_id,
            user_id=None,
        )

        folder_row = MagicMock()
        folder_row.id = folder_id
        folder_row.parent_id = None
        folder_row.name = "Folder"
        folder_row.fs_path = str(tmp_path / "Folder")
        folder_row.path = "Folder"

        photo = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=other_folder_id,
            filename="photo.jpg",
            deleted_at=None,
        )

        zip_root = tmp_path / "zips"
        zip_root.mkdir()
        (tmp_path / "Folder").mkdir(parents=True, exist_ok=True)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(job),
                MagicMock(),
                _fetchall([folder_row]),
                _scalars_all([photo]),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        with (
            patch.object(photos_zip_jobs, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_zip_jobs.photos_storage, "ZIPS_ROOT", zip_root),
            patch.object(
                photos_zip_jobs.photos_storage,
                "folder_fs_path",
                return_value=tmp_path / "Folder",
            ),
        ):
            await photos_zip_jobs.generate_folder_zip({}, str(job.id))

        zip_files = list(zip_root.glob("*.zip"))
        assert len(zip_files) == 1
