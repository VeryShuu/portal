from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import photos_trash_files as trash_files


def _make_photo(folder_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        filename="photo.jpg",
        folder_id=folder_id or uuid.uuid4(),
    )


def _make_folder(fs_path="photos/vacation", path="vacation"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        fs_path=fs_path,
        path=path,
    )


class TestOriginalPathFor:
    def test_returns_none_when_folder_is_none(self):
        photo = _make_photo()
        result = trash_files._original_path_for(photo, None)
        assert result is None

    def test_returns_path_when_folder_present(self, tmp_path):
        photo = _make_photo()
        folder = _make_folder(fs_path="vacation", path="vacation")
        with patch.object(
            trash_files.photos_storage,
            "folder_fs_path",
            return_value=tmp_path,
        ):
            result = trash_files._original_path_for(photo, folder)
        assert result == tmp_path / photo.filename

    def test_returns_none_on_value_error(self):
        photo = _make_photo()
        folder = _make_folder()
        with patch.object(
            trash_files.photos_storage,
            "folder_fs_path",
            side_effect=ValueError("Invalid folder path"),
        ):
            result = trash_files._original_path_for(photo, folder)
        assert result is None


class TestDeletePhotoFiles:
    @pytest.mark.asyncio
    async def test_calls_to_thread(self, tmp_path):
        photo = _make_photo()
        folder = _make_folder()
        fake_path = tmp_path / "photo.jpg"

        with (
            patch.object(
                trash_files.photos_storage,
                "folder_fs_path",
                return_value=tmp_path,
            ),
            patch("app.services.photos_trash_files.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            await trash_files.delete_photo_files(photo, folder)
        mock_thread.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_folder_still_calls(self):
        photo = _make_photo()
        with patch(
            "app.services.photos_trash_files.asyncio.to_thread", new_callable=AsyncMock
        ) as mock_thread:
            await trash_files.delete_photo_files(photo, None)
        mock_thread.assert_awaited_once()


class TestDeleteManyPhotoFiles:
    @pytest.mark.asyncio
    async def test_calls_delete_for_each_photo(self):
        photos = [_make_photo(), _make_photo()]
        folder_by_id = {}
        with patch.object(
            trash_files,
            "delete_photo_files",
            new_callable=AsyncMock,
        ) as mock_del:
            await trash_files.delete_many_photo_files(photos, folder_by_id)
        assert mock_del.call_count == 2

    @pytest.mark.asyncio
    async def test_logs_exception_and_continues(self):
        photo1 = _make_photo()
        photo2 = _make_photo()

        async def raise_first(photo, folder):
            if photo is photo1:
                raise RuntimeError("disk error")

        with patch.object(
            trash_files, "delete_photo_files", side_effect=raise_first
        ):
            await trash_files.delete_many_photo_files([photo1, photo2], {})

    @pytest.mark.asyncio
    async def test_empty_list_does_nothing(self):
        with patch.object(
            trash_files, "delete_photo_files", new_callable=AsyncMock
        ) as mock_del:
            await trash_files.delete_many_photo_files([], {})
        mock_del.assert_not_called()


class TestRmtreeFolderFs:
    @pytest.mark.asyncio
    async def test_calls_rmtree_when_dir_exists(self, tmp_path):
        folder = _make_folder()
        existing_dir = tmp_path / "vacation"
        existing_dir.mkdir()

        with (
            patch.object(
                trash_files.photos_storage,
                "folder_fs_path",
                return_value=existing_dir,
            ),
            patch("app.services.photos_trash_files.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            await trash_files.rmtree_folder_fs(folder)
        mock_thread.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_dir_not_exists(self, tmp_path):
        folder = _make_folder()
        missing_dir = tmp_path / "nonexistent"

        with (
            patch.object(
                trash_files.photos_storage,
                "folder_fs_path",
                return_value=missing_dir,
            ),
            patch("app.services.photos_trash_files.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            await trash_files.rmtree_folder_fs(folder)
        mock_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_on_value_error(self):
        folder = _make_folder()
        with patch.object(
            trash_files.photos_storage,
            "folder_fs_path",
            side_effect=ValueError("Invalid folder path"),
        ):
            await trash_files.rmtree_folder_fs(folder)

    @pytest.mark.asyncio
    async def test_logs_rmtree_exception(self, tmp_path):
        folder = _make_folder()
        existing_dir = tmp_path / "vacation"
        existing_dir.mkdir()

        with (
            patch.object(
                trash_files.photos_storage,
                "folder_fs_path",
                return_value=existing_dir,
            ),
            patch(
                "app.services.photos_trash_files.asyncio.to_thread",
                new_callable=AsyncMock,
                side_effect=OSError("busy"),
            ),
        ):
            await trash_files.rmtree_folder_fs(folder)

    @pytest.mark.asyncio
    async def test_uses_path_field_fallback(self, tmp_path):
        folder = SimpleNamespace(id=uuid.uuid4(), fs_path=None, path="vacation")
        existing_dir = tmp_path / "vacation"
        existing_dir.mkdir()

        with (
            patch.object(
                trash_files.photos_storage,
                "folder_fs_path",
                return_value=existing_dir,
            ),
            patch("app.services.photos_trash_files.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            await trash_files.rmtree_folder_fs(folder)
        mock_thread.assert_awaited_once()
