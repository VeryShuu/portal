from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import photos_photo_repo as repo


def _execute_scalars_all(values):
    inner = MagicMock()
    inner.all.return_value = values
    res = MagicMock()
    res.scalars.return_value = inner
    return res


def _execute_scalar_one_or_none(value):
    res = MagicMock()
    res.scalar_one_or_none.return_value = value
    return res


def _execute_all(rows):
    res = MagicMock()
    res.all.return_value = rows
    return res


def _execute_one(row):
    res = MagicMock()
    res.one.return_value = row
    return res


class TestFetchActivePhoto:
    @pytest.mark.asyncio
    async def test_found(self):
        photo = SimpleNamespace(id=uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalar_one_or_none(photo))
        result = await repo.fetch_active_photo(db, photo.id)
        assert result is photo

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalar_one_or_none(None))
        result = await repo.fetch_active_photo(db, uuid.uuid4())
        assert result is None


class TestFetchPhotoAny:
    @pytest.mark.asyncio
    async def test_found(self):
        photo = SimpleNamespace(id=uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalar_one_or_none(photo))
        result = await repo.fetch_photo_any(db, photo.id)
        assert result is photo

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalar_one_or_none(None))
        result = await repo.fetch_photo_any(db, uuid.uuid4())
        assert result is None


class TestFetchFolder:
    @pytest.mark.asyncio
    async def test_found(self):
        folder = SimpleNamespace(id=uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalar_one_or_none(folder))
        result = await repo.fetch_folder(db, folder.id)
        assert result is folder

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalar_one_or_none(None))
        result = await repo.fetch_folder(db, uuid.uuid4())
        assert result is None


class TestFetchActiveFolder:
    @pytest.mark.asyncio
    async def test_found(self):
        folder = SimpleNamespace(id=uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalar_one_or_none(folder))
        result = await repo.fetch_active_folder(db, folder.id)
        assert result is folder

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalar_one_or_none(None))
        result = await repo.fetch_active_folder(db, uuid.uuid4())
        assert result is None


class TestCountFolderPhotos:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=10)
        result = await repo.count_folder_photos(
            db,
            uuid.uuid4(),
            min_date=None,
            max_date=None,
            min_size=None,
            max_size=None,
            mime_type=None,
        )
        assert result == 10

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        result = await repo.count_folder_photos(
            db,
            uuid.uuid4(),
            min_date=None,
            max_date=None,
            min_size=None,
            max_size=None,
            mime_type=None,
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_with_all_filters(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=5)
        now = datetime.now(UTC)
        result = await repo.count_folder_photos(
            db,
            uuid.uuid4(),
            min_date=now,
            max_date=now,
            min_size=100,
            max_size=10000,
            mime_type="image/jpeg",
            tag_id=uuid.uuid4(),
        )
        assert result == 5


class TestFetchFolderPhotosPage:
    @pytest.mark.asyncio
    async def test_returns_photos(self):
        photo = SimpleNamespace(id=uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalars_all([photo]))
        result = await repo.fetch_folder_photos_page(
            db,
            uuid.uuid4(),
            sort="created_at",
            min_date=None,
            max_date=None,
            min_size=None,
            max_size=None,
            mime_type=None,
            offset=0,
            limit=20,
        )
        assert list(result) == [photo]

    @pytest.mark.asyncio
    async def test_sort_by_taken_at(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalars_all([]))
        result = await repo.fetch_folder_photos_page(
            db,
            uuid.uuid4(),
            sort="taken_at",
            min_date=None,
            max_date=None,
            min_size=None,
            max_size=None,
            mime_type=None,
            offset=0,
            limit=10,
        )
        assert list(result) == []

    @pytest.mark.asyncio
    async def test_sort_by_original_name(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalars_all([]))
        await repo.fetch_folder_photos_page(
            db,
            uuid.uuid4(),
            sort="original_name",
            min_date=None,
            max_date=None,
            min_size=None,
            max_size=None,
            mime_type=None,
            offset=5,
            limit=10,
        )
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_tag_id(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalars_all([]))
        await repo.fetch_folder_photos_page(
            db,
            uuid.uuid4(),
            sort="created_at",
            min_date=None,
            max_date=None,
            min_size=None,
            max_size=None,
            mime_type=None,
            offset=0,
            limit=10,
            tag_id=uuid.uuid4(),
        )
        db.execute.assert_called_once()


class TestCountDeletedPhotosAdmin:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=7)
        result = await repo.count_deleted_photos_admin(db, datetime.now(UTC))
        assert result == 7

    @pytest.mark.asyncio
    async def test_none_returns_zero(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        result = await repo.count_deleted_photos_admin(db, datetime.now(UTC))
        assert result == 0


class TestFetchDeletedPhotosAdminPage:
    @pytest.mark.asyncio
    async def test_returns_pairs(self):
        photo = SimpleNamespace(id=uuid.uuid4())
        folder = SimpleNamespace(id=uuid.uuid4())
        row = MagicMock()
        row.__getitem__ = lambda self, i: [photo, folder][i]
        res = MagicMock()
        res.all.return_value = [row]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_deleted_photos_admin_page(
            db, datetime.now(UTC), offset=0, limit=10
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_empty(self):
        res = MagicMock()
        res.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_deleted_photos_admin_page(
            db, datetime.now(UTC), offset=0, limit=10
        )
        assert result == []


class TestFetchDeletedPhotosWithFolders:
    @pytest.mark.asyncio
    async def test_returns_pairs(self):
        photo = SimpleNamespace(id=uuid.uuid4())
        folder = SimpleNamespace(id=uuid.uuid4())
        row = MagicMock()
        row.__getitem__ = lambda self, i: [photo, folder][i]
        res = MagicMock()
        res.all.return_value = [row]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_deleted_photos_with_folders(db, datetime.now(UTC))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_empty(self):
        res = MagicMock()
        res.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_deleted_photos_with_folders(db, datetime.now(UTC))
        assert result == []


class TestFetchRecentPhotosWithFolders:
    @pytest.mark.asyncio
    async def test_returns_pairs(self):
        photo = SimpleNamespace(id=uuid.uuid4())
        folder = SimpleNamespace(id=uuid.uuid4())
        row = MagicMock()
        row.__getitem__ = lambda self, i: [photo, folder][i]
        res = MagicMock()
        res.all.return_value = [row]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_recent_photos_with_folders(db, limit=10)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_empty(self):
        res = MagicMock()
        res.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_recent_photos_with_folders(db, limit=10, offset=5)
        assert result == []


class TestFetchStorageStatsTopFolders:
    @pytest.mark.asyncio
    async def test_returns_rows(self):
        fid = uuid.uuid4()
        row = (fid, "Vacation", "vacation", 1024, 5)
        res = MagicMock()
        res.all.return_value = [row]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_storage_stats_top_folders(db, limit=10)
        assert result == [row]

    @pytest.mark.asyncio
    async def test_empty(self):
        res = MagicMock()
        res.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_storage_stats_top_folders(db)
        assert result == []


class TestFetchGlobalStorageTotals:
    @pytest.mark.asyncio
    async def test_returns_totals(self):
        res = MagicMock()
        res.one.return_value = (10240, 42)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        total_size, total_files = await repo.fetch_global_storage_totals(db)
        assert total_size == 10240
        assert total_files == 42


class TestFetchStorageStats:
    @pytest.mark.asyncio
    async def test_returns_dict(self):
        fid = uuid.uuid4()
        top_row = (fid, "Vacation", "vacation", 1024, 5)
        res_top = MagicMock()
        res_top.all.return_value = [top_row]
        res_totals = MagicMock()
        res_totals.one.return_value = (2048, 10)
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[res_top, res_totals])
        result = await repo.fetch_storage_stats(db, top_limit=50)
        assert result["total_size_bytes"] == 2048
        assert result["total_files"] == 10
        assert len(result["top_folders"]) == 1
        assert result["top_folders"][0]["folder_name"] == "Vacation"


class TestFetchActivePhotosMap:
    @pytest.mark.asyncio
    async def test_returns_map(self):
        pid = uuid.uuid4()
        photo = SimpleNamespace(id=pid)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalars_all([photo]))
        result = await repo.fetch_active_photos_map(db, [pid])
        assert result == {pid: photo}

    @pytest.mark.asyncio
    async def test_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalars_all([]))
        result = await repo.fetch_active_photos_map(db, [])
        assert result == {}


class TestFetchFoldersMap:
    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        result = await repo.fetch_folders_map(db, set())
        assert result == {}
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_map(self):
        fid = uuid.uuid4()
        folder = SimpleNamespace(id=fid)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_execute_scalars_all([folder]))
        result = await repo.fetch_folders_map(db, {fid})
        assert result == {fid: folder}


class TestPurgePhotoRow:
    @pytest.mark.asyncio
    async def test_calls_execute_twice(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        await repo.purge_photo_row(db, uuid.uuid4())
        assert db.execute.call_count == 2
