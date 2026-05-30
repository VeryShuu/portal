from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import photos_folder_repo as repo


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


def _make_db(execute_return=None, scalar_return=None):
    db = AsyncMock()
    if execute_return is not None:
        db.execute = AsyncMock(return_value=execute_return)
    if scalar_return is not None:
        db.scalar = AsyncMock(return_value=scalar_return)
    return db


class TestFetchActiveFoldersOrdered:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        folder = SimpleNamespace(id=uuid.uuid4())
        db = _make_db(execute_return=_execute_scalars_all([folder]))
        result = await repo.fetch_active_folders_ordered(db)
        assert list(result) == [folder]

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db(execute_return=_execute_scalars_all([]))
        result = await repo.fetch_active_folders_ordered(db)
        assert list(result) == []


class TestFetchDeletedFoldersOrdered:
    @pytest.mark.asyncio
    async def test_returns_deleted_folders(self):
        folder = SimpleNamespace(id=uuid.uuid4(), deleted_at=datetime.now(UTC))
        db = _make_db(execute_return=_execute_scalars_all([folder]))
        result = await repo.fetch_deleted_folders_ordered(db)
        assert list(result) == [folder]


class TestFetchActiveFolder:
    @pytest.mark.asyncio
    async def test_found(self):
        folder = SimpleNamespace(id=uuid.uuid4())
        db = _make_db(execute_return=_execute_scalar_one_or_none(folder))
        result = await repo.fetch_active_folder(db, folder.id)
        assert result is folder

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = _make_db(execute_return=_execute_scalar_one_or_none(None))
        result = await repo.fetch_active_folder(db, uuid.uuid4())
        assert result is None


class TestFetchFolderAny:
    @pytest.mark.asyncio
    async def test_found(self):
        folder = SimpleNamespace(id=uuid.uuid4())
        db = _make_db(execute_return=_execute_scalar_one_or_none(folder))
        result = await repo.fetch_folder_any(db, folder.id)
        assert result is folder

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = _make_db(execute_return=_execute_scalar_one_or_none(None))
        result = await repo.fetch_folder_any(db, uuid.uuid4())
        assert result is None


class TestCountActivePhotosInFolder:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        db = _make_db(scalar_return=5)
        result = await repo.count_active_photos_in_folder(db, uuid.uuid4())
        assert result == 5

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        result = await repo.count_active_photos_in_folder(db, uuid.uuid4())
        assert result == 0


class TestCountActiveSubfolders:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        db = _make_db(scalar_return=3)
        result = await repo.count_active_subfolders(db, uuid.uuid4())
        assert result == 3

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        result = await repo.count_active_subfolders(db, uuid.uuid4())
        assert result == 0


class TestCountSiblingsWithSlug:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        db = _make_db(scalar_return=2)
        result = await repo.count_siblings_with_slug(
            db, parent_id=uuid.uuid4(), slug="my-folder"
        )
        assert result == 2

    @pytest.mark.asyncio
    async def test_with_exclude_id(self):
        db = _make_db(scalar_return=0)
        result = await repo.count_siblings_with_slug(
            db, parent_id=uuid.uuid4(), slug="test", exclude_id=uuid.uuid4()
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_none_parent_id(self):
        db = _make_db(scalar_return=1)
        result = await repo.count_siblings_with_slug(
            db, parent_id=None, slug="root"
        )
        assert result == 1


class TestFetchSiblingFsSegments:
    @pytest.mark.asyncio
    async def test_returns_segments(self):
        res = MagicMock()
        res.all.return_value = [("photos/vacation",), ("photos/summer",)]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_sibling_fs_segments(db, parent_id=uuid.uuid4())
        assert "vacation" in result
        assert "summer" in result

    @pytest.mark.asyncio
    async def test_empty(self):
        res = MagicMock()
        res.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_sibling_fs_segments(db, parent_id=uuid.uuid4())
        assert result == set()

    @pytest.mark.asyncio
    async def test_with_exclude_id(self):
        res = MagicMock()
        res.all.return_value = [("photos/other",)]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_sibling_fs_segments(
            db, parent_id=uuid.uuid4(), exclude_id=uuid.uuid4()
        )
        assert "other" in result


class TestFetchParentFsPath:
    @pytest.mark.asyncio
    async def test_returns_path(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value="photos/parent")
        result = await repo.fetch_parent_fs_path(db, uuid.uuid4())
        assert result == "photos/parent"

    @pytest.mark.asyncio
    async def test_none_becomes_empty_string(self):
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        result = await repo.fetch_parent_fs_path(db, uuid.uuid4())
        assert result == ""


class TestCascadeDescendantPaths:
    @pytest.mark.asyncio
    async def test_empty_old_path_skips_execute(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        await repo.cascade_descendant_paths(
            db, old_path="", new_path="new", old_fs_path=None, new_fs_path=None
        )
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_with_valid_path(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        await repo.cascade_descendant_paths(
            db, old_path="photos/old", new_path="photos/new",
            old_fs_path="old_fs", new_fs_path="new_fs"
        )
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_executes_without_fs_path(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        await repo.cascade_descendant_paths(
            db, old_path="photos/old", new_path="photos/new",
            old_fs_path=None, new_fs_path=None
        )
        db.execute.assert_called_once()


class TestCascadeDescendantFsPaths:
    @pytest.mark.asyncio
    async def test_empty_old_fs_path_skips_execute(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        await repo.cascade_descendant_fs_paths(db, old_fs_path="", new_fs_path="new")
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_with_valid_path(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        await repo.cascade_descendant_fs_paths(
            db, old_fs_path="photos/old", new_fs_path="photos/new"
        )
        db.execute.assert_called_once()


class TestFetchCoverPhotoInFolder:
    @pytest.mark.asyncio
    async def test_found(self):
        photo = SimpleNamespace(id=uuid.uuid4())
        db = _make_db(execute_return=_execute_scalar_one_or_none(photo))
        result = await repo.fetch_cover_photo_in_folder(
            db, folder_id=uuid.uuid4(), photo_id=photo.id
        )
        assert result is photo

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = _make_db(execute_return=_execute_scalar_one_or_none(None))
        result = await repo.fetch_cover_photo_in_folder(
            db, folder_id=uuid.uuid4(), photo_id=uuid.uuid4()
        )
        assert result is None


class TestFetchDescendantIds:
    @pytest.mark.asyncio
    async def test_returns_ids(self):
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        res = MagicMock()
        res.fetchall.return_value = [(id1,), (id2,)]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_descendant_ids(db, uuid.uuid4())
        assert result == [id1, id2]

    @pytest.mark.asyncio
    async def test_empty(self):
        res = MagicMock()
        res.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=res)
        result = await repo.fetch_descendant_ids(db, uuid.uuid4())
        assert result == []


class TestSoftDeleteFolderPhotos:
    @pytest.mark.asyncio
    async def test_calls_execute(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        ts = datetime.now(UTC)
        await repo.soft_delete_folder_photos(db, folder_id=uuid.uuid4(), ts=ts)
        db.execute.assert_called_once()


class TestRestoreDescendants:
    @pytest.mark.asyncio
    async def test_empty_ids_skips(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        await repo.restore_descendants(db, descendant_ids=[], cascade_ts=datetime.now(UTC))
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_empty_calls_execute_twice(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        ids = [uuid.uuid4(), uuid.uuid4()]
        await repo.restore_descendants(db, descendant_ids=ids, cascade_ts=datetime.now(UTC))
        assert db.execute.call_count == 2


class TestRestoreDirectPhotos:
    @pytest.mark.asyncio
    async def test_calls_execute(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        await repo.restore_direct_photos(
            db, folder_id=uuid.uuid4(), cascade_ts=datetime.now(UTC)
        )
        db.execute.assert_called_once()


class TestFetchPhotosInFolders:
    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        result = await repo.fetch_photos_in_folders(db, [])
        assert list(result) == []
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_photos(self):
        photo = SimpleNamespace(id=uuid.uuid4())
        db = _make_db(execute_return=_execute_scalars_all([photo]))
        result = await repo.fetch_photos_in_folders(db, [uuid.uuid4()])
        assert list(result) == [photo]


class TestFetchFoldersByIds:
    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        result = await repo.fetch_folders_by_ids(db, [])
        assert list(result) == []
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_folders(self):
        folder = SimpleNamespace(id=uuid.uuid4())
        db = _make_db(execute_return=_execute_scalars_all([folder]))
        result = await repo.fetch_folders_by_ids(db, [folder.id])
        assert list(result) == [folder]
