from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks.photos import processing as photos_processing


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


class TestProcessPhotoUpload:
    @pytest.mark.asyncio
    async def test_lock_not_acquired_returns_early(self):
        pool = AsyncMock()
        pool.set = AsyncMock(return_value=False)
        pool.delete = AsyncMock()

        ctx = {"redis": pool}
        with patch.object(photos_processing, "AsyncSessionLocal") as mock_session:
            await photos_processing.process_photo_upload(ctx, str(uuid.uuid4()))

        mock_session.assert_not_called()
        pool.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_acquired_then_released(self, tmp_path):
        photo_id = uuid.uuid4()
        photo = SimpleNamespace(
            id=photo_id,
            deleted_at=None,
            folder_id=uuid.uuid4(),
            filename="x.jpg",
            processed=True,
            blurhash="abc",
            width=100,
            height=100,
            exif={"key": "val"},
        )

        pool = AsyncMock()
        pool.set = AsyncMock(return_value=True)
        pool.delete = AsyncMock()

        thumb_dir = tmp_path / str(photo_id)
        thumb_dir.mkdir()
        (thumb_dir / "200.webp").write_bytes(b"thumb")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(photo))
        db.commit = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            await photos_processing.process_photo_upload({"redis": pool}, str(photo_id))

        pool.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lock_acquire_exception_continues(self, tmp_path):
        photo_id = uuid.uuid4()
        photo = SimpleNamespace(
            id=photo_id,
            deleted_at=None,
            folder_id=uuid.uuid4(),
            filename="x.jpg",
            processed=True,
            blurhash="abc",
            width=100,
            height=100,
            exif={"k": "v"},
        )

        pool = AsyncMock()
        pool.set = AsyncMock(side_effect=Exception("redis down"))
        pool.delete = AsyncMock()

        thumb_dir = tmp_path / str(photo_id)
        thumb_dir.mkdir()
        (thumb_dir / "200.webp").write_bytes(b"thumb")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(photo))
        db.commit = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            await photos_processing.process_photo_upload({"redis": pool}, str(photo_id))

        pool.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_inner_exception_is_logged_not_reraised(self, tmp_path):
        pool = AsyncMock()
        pool.set = AsyncMock(return_value=True)
        pool.delete = AsyncMock()

        with patch.object(
            photos_processing,
            "_process_photo_upload_inner",
            side_effect=ValueError("inner error"),
        ):
            await photos_processing.process_photo_upload({"redis": pool}, str(uuid.uuid4()))

        pool.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancelled_error_is_reraised(self):
        pool = AsyncMock()
        pool.set = AsyncMock(return_value=True)
        pool.delete = AsyncMock()

        with patch.object(
            photos_processing,
            "_process_photo_upload_inner",
            side_effect=asyncio.CancelledError(),
        ):
            with pytest.raises(asyncio.CancelledError):
                await photos_processing.process_photo_upload({"redis": pool}, str(uuid.uuid4()))

        pool.delete.assert_awaited_once()


class TestProcessPhotoUploadInner:
    @pytest.mark.asyncio
    async def test_already_processed_with_thumb_and_blurhash_returns_early(self, tmp_path):
        photo_id = uuid.uuid4()
        photo = SimpleNamespace(
            id=photo_id,
            deleted_at=None,
            folder_id=uuid.uuid4(),
            filename="x.jpg",
            processed=True,
            blurhash="abc",
            width=100,
            height=100,
            exif={"k": "v"},
        )

        thumb_dir = tmp_path / str(photo_id)
        thumb_dir.mkdir()
        (thumb_dir / "200.webp").write_bytes(b"thumb")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none(photo))
        db.commit = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            await photos_processing._process_photo_upload_inner({}, photo_id, str(photo_id))

        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_folder_not_found_returns_early(self, tmp_path):
        photo_id = uuid.uuid4()
        photo = SimpleNamespace(
            id=photo_id,
            deleted_at=None,
            folder_id=uuid.uuid4(),
            filename="x.jpg",
            processed=False,
            blurhash=None,
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(photo),
                _scalar_one_or_none(None),
            ]
        )
        db.commit = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            await photos_processing._process_photo_upload_inner({}, photo_id, str(photo_id))

        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_original_and_thumb_returns_early(self, tmp_path):
        photo_id = uuid.uuid4()
        photo = SimpleNamespace(
            id=photo_id,
            deleted_at=None,
            folder_id=uuid.uuid4(),
            filename="x.jpg",
            processed=False,
            blurhash=None,
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
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
            patch.object(
                photos_processing.photos_storage,
                "folder_fs_path",
                return_value=tmp_path / "missing",
            ),
        ):
            await photos_processing._process_photo_upload_inner({}, photo_id, str(photo_id))

        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_thumb_gen_success_sets_processed_true(self, tmp_path):
        photo_id = uuid.uuid4()
        photo = SimpleNamespace(
            id=photo_id,
            deleted_at=None,
            folder_id=uuid.uuid4(),
            filename="x.jpg",
            processed=False,
            blurhash=None,
            width=None,
            height=None,
            exif=None,
        )
        folder = SimpleNamespace(fs_path=str(tmp_path), path="")

        original = tmp_path / "x.jpg"
        original.write_bytes(b"img")

        thumb_dir = tmp_path / str(photo_id)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(photo),
                _scalar_one_or_none(folder),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
            patch.object(
                photos_processing.photos_storage,
                "folder_fs_path",
                return_value=tmp_path,
            ),
            patch.object(
                photos_processing.photos_storage,
                "generate_thumbnails",
                return_value={200: thumb_dir / "200.webp"},
            ),
            patch.object(
                photos_processing.photos_storage,
                "compute_blurhash",
                return_value="blurhash123",
            ),
            patch.object(
                photos_processing.photos_storage,
                "extract_exif",
                return_value=({"Make": "Canon"}, (1920, 1080), "2024-01-01T00:00:00"),
            ),
            patch("app.worker.tasks.photos.processing.publish_photo_processed", new=AsyncMock()),
            patch(
                "app.core.modules_config.load_modules",
                return_value=MagicMock(photos=MagicMock(strip_gps=True)),
            ),
        ):
            await photos_processing._process_photo_upload_inner({}, photo_id, str(photo_id))

        db.commit.assert_awaited_once()
        update_call = db.execute.call_args_list[-1]
        assert update_call is not None

    @pytest.mark.asyncio
    async def test_thumb_gen_failure_still_marks_processed(self, tmp_path):
        photo_id = uuid.uuid4()
        photo = SimpleNamespace(
            id=photo_id,
            deleted_at=None,
            folder_id=uuid.uuid4(),
            filename="x.jpg",
            processed=False,
            blurhash=None,
            width=None,
            height=None,
            exif=None,
        )
        folder = SimpleNamespace(fs_path=str(tmp_path), path="")

        original = tmp_path / "x.jpg"
        original.write_bytes(b"img")

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(photo),
                _scalar_one_or_none(folder),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
            patch.object(
                photos_processing.photos_storage,
                "folder_fs_path",
                return_value=tmp_path,
            ),
            patch.object(
                photos_processing.photos_storage,
                "generate_thumbnails",
                side_effect=OSError("disk full"),
            ),
            patch.object(
                photos_processing.photos_storage,
                "extract_exif",
                return_value=({}, None, None),
            ),
            patch(
                "app.core.modules_config.load_modules",
                return_value=MagicMock(photos=MagicMock(strip_gps=True)),
            ),
        ):
            await photos_processing._process_photo_upload_inner({}, photo_id, str(photo_id))

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sse_published_with_redis(self, tmp_path):
        photo_id = uuid.uuid4()
        folder_id = uuid.uuid4()
        photo = SimpleNamespace(
            id=photo_id,
            deleted_at=None,
            folder_id=folder_id,
            filename="x.jpg",
            processed=False,
            blurhash=None,
            width=None,
            height=None,
            exif=None,
        )
        folder = SimpleNamespace(fs_path=str(tmp_path), path="")

        original = tmp_path / "x.jpg"
        original.write_bytes(b"img")

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(photo),
                _scalar_one_or_none(folder),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        mock_publish = AsyncMock()
        pool = MagicMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
            patch.object(
                photos_processing.photos_storage,
                "folder_fs_path",
                return_value=tmp_path,
            ),
            patch.object(
                photos_processing.photos_storage,
                "generate_thumbnails",
                side_effect=OSError("fail"),
            ),
            patch.object(
                photos_processing.photos_storage,
                "extract_exif",
                return_value=({}, None, None),
            ),
            patch.object(photos_processing, "publish_photo_processed", mock_publish),
            patch(
                "app.core.modules_config.load_modules",
                return_value=MagicMock(photos=MagicMock(strip_gps=True)),
            ),
        ):
            await photos_processing._process_photo_upload_inner({"redis": pool}, photo_id, str(photo_id))

        mock_publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_thumbs_exist_no_original_still_processes(self, tmp_path):
        photo_id = uuid.uuid4()
        photo = SimpleNamespace(
            id=photo_id,
            deleted_at=None,
            folder_id=uuid.uuid4(),
            filename="x.jpg",
            processed=False,
            blurhash=None,
            width=None,
            height=None,
            exif=None,
        )
        folder = SimpleNamespace(fs_path=str(tmp_path / "missing"), path="missing")

        thumb_dir = tmp_path / str(photo_id)
        thumb_dir.mkdir()
        (thumb_dir / "200.webp").write_bytes(b"thumb")

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(photo),
                _scalar_one_or_none(folder),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
            patch.object(
                photos_processing.photos_storage,
                "folder_fs_path",
                return_value=tmp_path / "missing",
            ),
            patch.object(
                photos_processing.photos_storage,
                "compute_blurhash",
                return_value="hash",
            ),
        ):
            await photos_processing._process_photo_upload_inner({}, photo_id, str(photo_id))

        db.commit.assert_awaited_once()


class TestDetectMissingThumbnails:
    @pytest.mark.asyncio
    async def test_empty_batch(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_all([]))
        with patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)):
            out = await photos_processing.detect_missing_thumbnails({"redis": MagicMock()})
        assert out == {"requeued": 0, "healed": 0}

    @pytest.mark.asyncio
    async def test_no_redis_pool_short_circuits(self):
        out = await photos_processing.detect_missing_thumbnails({})
        assert out == {"requeued": 0, "healed": 0}

    @pytest.mark.asyncio
    async def test_heal_path_processed_false_thumb_exists(self, tmp_path):
        photo = SimpleNamespace(
            id=uuid.uuid4(),
            processed=False,
            blurhash="hash",
            created_at=datetime.now(UTC),
        )

        thumb_dir = tmp_path / str(photo.id)
        thumb_dir.mkdir(parents=True)
        (thumb_dir / "200.webp").write_bytes(b"thumb")

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([photo]),
                MagicMock(),
                _scalars_all([]),
            ]
        )
        db.commit = AsyncMock()
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()
        pool.exists = AsyncMock(return_value=0)

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_processing.detect_missing_thumbnails({"redis": pool})

        assert out["healed"] == 1
        pool.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_heal_path_missing_blurhash_requeues(self, tmp_path):
        photo = SimpleNamespace(
            id=uuid.uuid4(),
            processed=False,
            blurhash=None,
            created_at=datetime.now(UTC),
        )

        thumb_dir = tmp_path / str(photo.id)
        thumb_dir.mkdir(parents=True)
        (thumb_dir / "200.webp").write_bytes(b"thumb")

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([photo]),
                MagicMock(),
                _scalars_all([]),
            ]
        )
        db.commit = AsyncMock()
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()
        pool.exists = AsyncMock(return_value=0)

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_processing.detect_missing_thumbnails({"redis": pool})

        assert out["healed"] == 1
        pool.enqueue_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_give_up_path_old_photo_with_missing_thumb(self, tmp_path):
        photo = SimpleNamespace(
            id=uuid.uuid4(),
            processed=True,
            blurhash=None,
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([photo]),
                _scalars_all([]),
            ]
        )
        db.commit = AsyncMock()
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()
        pool.exists = AsyncMock(return_value=0)

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_processing.detect_missing_thumbnails({"redis": pool})

        assert out["requeued"] == 0
        pool.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_held_skips_enqueue(self, tmp_path):
        photo = SimpleNamespace(
            id=uuid.uuid4(),
            processed=True,
            blurhash=None,
            created_at=datetime.now(UTC),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([photo]),
                MagicMock(),
                _scalars_all([]),
            ]
        )
        db.commit = AsyncMock()
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()
        pool.exists = AsyncMock(return_value=1)

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_processing.detect_missing_thumbnails({"redis": pool})

        assert out["requeued"] == 0
        pool.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueue_failure_is_logged_not_raised(self, tmp_path):
        photo = SimpleNamespace(
            id=uuid.uuid4(),
            processed=False,
            blurhash=None,
            created_at=datetime.now(UTC),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([photo]),
                _scalars_all([]),
            ]
        )
        db.commit = AsyncMock()
        pool = MagicMock()
        pool.enqueue_job = AsyncMock(side_effect=Exception("redis down"))
        pool.exists = AsyncMock(return_value=0)

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_processing.detect_missing_thumbnails({"redis": pool})

        assert out["requeued"] == 0

    @pytest.mark.asyncio
    async def test_reset_failed_logs_and_continues(self, tmp_path):
        photo = SimpleNamespace(
            id=uuid.uuid4(),
            processed=True,
            blurhash=None,
            created_at=datetime.now(UTC),
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([photo]),
                Exception("update failed"),
                _scalars_all([]),
            ]
        )
        db.commit = AsyncMock()
        pool = MagicMock()
        pool.enqueue_job = AsyncMock()
        pool.exists = AsyncMock(return_value=0)

        with (
            patch.object(photos_processing, "AsyncSessionLocal", return_value=_session_cm(db)),
            patch.object(photos_processing.photos_storage, "THUMBS_ROOT", tmp_path),
        ):
            out = await photos_processing.detect_missing_thumbnails({"redis": pool})

        assert out is not None
