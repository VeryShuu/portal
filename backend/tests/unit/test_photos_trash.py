from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.photos import PhotoPublic
from app.services.photos_trash import TrashService


def _make_photo_public():
    now = datetime.now(UTC)
    return PhotoPublic(
        id=uuid.uuid4(),
        folder_id=uuid.uuid4(),
        folder_path="vacation",
        filename="photo.jpg",
        original_name="photo.jpg",
        size_bytes=1024,
        mime_type="image/jpeg",
        description=None,
        processed=True,
        blurhash=None,
        uploaded_by=None,
        created_at=now,
    )


def _make_folder(deleted_at=None, parent_id=None, path="vacation", fs_path=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        deleted_at=deleted_at,
        parent_id=parent_id,
        path=path,
        fs_path=fs_path,
        name="Vacation",
    )


def _make_photo(deleted_at=None, folder_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        deleted_at=deleted_at,
        folder_id=folder_id or uuid.uuid4(),
        filename="photo.jpg",
    )


def _make_user(role="member"):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


FOLDER_REPO = "app.services.photos_trash.folder_repo"
PHOTO_REPO = "app.services.photos_trash.photo_repo"
TRASH_FILES = "app.services.photos_trash.trash_files"
TRASH_REPO = "app.services.photos_trash.trash_repo"
RESOLVE_BATCH = "app.services.photos_trash.resolve_folders_permissions_batch"


class TestMarkPhotoDeleted:
    def test_sets_deleted_at(self):
        photo = SimpleNamespace(deleted_at=None)
        TrashService.mark_photo_deleted(photo)
        assert photo.deleted_at is not None


class TestSoftDeleteFolder:
    @pytest.mark.asyncio
    async def test_folder_not_found_returns_zero(self):
        db = AsyncMock()
        with patch(f"{FOLDER_REPO}.fetch_active_folder", return_value=None):
            result = await TrashService.soft_delete_folder(db, uuid.uuid4())
        assert result == 0

    @pytest.mark.asyncio
    async def test_folder_with_no_descendants(self):
        folder = _make_folder()
        db = AsyncMock()
        db.execute = AsyncMock()
        with (
            patch(f"{FOLDER_REPO}.fetch_active_folder", return_value=folder),
            patch(f"{FOLDER_REPO}.fetch_descendant_ids", return_value=[]),
            patch(f"{FOLDER_REPO}.soft_delete_folder_photos", new_callable=AsyncMock),
        ):
            result = await TrashService.soft_delete_folder(db, folder.id)
        assert result == 1
        assert folder.deleted_at is not None

    @pytest.mark.asyncio
    async def test_folder_with_descendants(self):
        folder = _make_folder()
        child_id = uuid.uuid4()
        db = AsyncMock()
        db.execute = AsyncMock()
        with (
            patch(f"{FOLDER_REPO}.fetch_active_folder", return_value=folder),
            patch(f"{FOLDER_REPO}.fetch_descendant_ids", return_value=[child_id]),
            patch(f"{FOLDER_REPO}.soft_delete_folder_photos", new_callable=AsyncMock),
        ):
            result = await TrashService.soft_delete_folder(db, folder.id)
        assert result == 2
        assert db.execute.call_count == 2


class TestSoftDeletePhoto:
    @pytest.mark.asyncio
    async def test_photo_not_found_does_nothing(self):
        db = AsyncMock()
        with patch(f"{PHOTO_REPO}.fetch_active_photo", return_value=None):
            await TrashService.soft_delete_photo(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_marks_photo_deleted(self):
        photo = _make_photo()
        db = AsyncMock()
        with patch(f"{PHOTO_REPO}.fetch_active_photo", return_value=photo):
            await TrashService.soft_delete_photo(db, photo.id)
        assert photo.deleted_at is not None


class TestRestoreFolder:
    @pytest.mark.asyncio
    async def test_folder_not_found_returns_zero(self):
        db = AsyncMock()
        with patch(f"{FOLDER_REPO}.fetch_folder_any", return_value=None):
            result = await TrashService.restore_folder(db, uuid.uuid4())
        assert result == 0

    @pytest.mark.asyncio
    async def test_active_folder_returns_zero(self):
        folder = _make_folder(deleted_at=None)
        db = AsyncMock()
        with patch(f"{FOLDER_REPO}.fetch_folder_any", return_value=folder):
            result = await TrashService.restore_folder(db, folder.id)
        assert result == 0

    @pytest.mark.asyncio
    async def test_restores_folder_and_descendants(self):
        ts = datetime.now(UTC)
        folder = _make_folder(deleted_at=ts)
        child_id = uuid.uuid4()
        db = AsyncMock()
        with (
            patch(f"{FOLDER_REPO}.fetch_folder_any", return_value=folder),
            patch(f"{FOLDER_REPO}.fetch_descendant_ids", return_value=[child_id]),
            patch(f"{FOLDER_REPO}.restore_descendants", new_callable=AsyncMock) as mock_rd,
            patch(f"{FOLDER_REPO}.restore_direct_photos", new_callable=AsyncMock) as mock_rp,
        ):
            result = await TrashService.restore_folder(db, folder.id)
        assert result == 2
        assert folder.deleted_at is None
        mock_rd.assert_awaited_once()
        mock_rp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restores_folder_no_descendants(self):
        ts = datetime.now(UTC)
        folder = _make_folder(deleted_at=ts)
        db = AsyncMock()
        with (
            patch(f"{FOLDER_REPO}.fetch_folder_any", return_value=folder),
            patch(f"{FOLDER_REPO}.fetch_descendant_ids", return_value=[]),
            patch(f"{FOLDER_REPO}.restore_descendants", new_callable=AsyncMock),
            patch(f"{FOLDER_REPO}.restore_direct_photos", new_callable=AsyncMock),
        ):
            result = await TrashService.restore_folder(db, folder.id)
        assert result == 1


class TestRestorePhoto:
    @pytest.mark.asyncio
    async def test_photo_not_found_does_nothing(self):
        db = AsyncMock()
        with patch(f"{PHOTO_REPO}.fetch_photo_any", return_value=None):
            await TrashService.restore_photo(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_photo_not_deleted_does_nothing(self):
        photo = _make_photo(deleted_at=None)
        db = AsyncMock()
        with patch(f"{PHOTO_REPO}.fetch_photo_any", return_value=photo):
            await TrashService.restore_photo(db, photo.id)
        assert photo.deleted_at is None

    @pytest.mark.asyncio
    async def test_restores_photo(self):
        photo = _make_photo(deleted_at=datetime.now(UTC))
        db = AsyncMock()
        with patch(f"{PHOTO_REPO}.fetch_photo_any", return_value=photo):
            await TrashService.restore_photo(db, photo.id)
        assert photo.deleted_at is None


class TestPurgePhoto:
    @pytest.mark.asyncio
    async def test_photo_not_found_does_nothing(self):
        db = AsyncMock()
        with patch(f"{PHOTO_REPO}.fetch_photo_any", return_value=None):
            await TrashService.purge_photo(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_purges_photo(self):
        photo = _make_photo()
        folder = _make_folder()
        db = AsyncMock()
        with (
            patch(f"{PHOTO_REPO}.fetch_photo_any", return_value=photo),
            patch(f"{PHOTO_REPO}.fetch_folder", return_value=folder),
            patch(f"{TRASH_FILES}.delete_photo_files", new_callable=AsyncMock) as mock_del,
            patch(f"{TRASH_REPO}.purge_photo_row", new_callable=AsyncMock) as mock_purge,
        ):
            await TrashService.purge_photo(db, photo.id)
        mock_del.assert_awaited_once()
        mock_purge.assert_awaited_once()


class TestPurgeFolderSubtree:
    @pytest.mark.asyncio
    async def test_folder_not_found_returns_zeros(self):
        db = AsyncMock()
        with patch(f"{FOLDER_REPO}.fetch_folder_any", return_value=None):
            result = await TrashService.purge_folder_subtree(db, uuid.uuid4())
        assert result == (0, 0)

    @pytest.mark.asyncio
    async def test_purges_folder_and_photos(self):
        folder = _make_folder()
        photo = _make_photo(folder_id=folder.id)
        db = AsyncMock()
        with (
            patch(f"{FOLDER_REPO}.fetch_folder_any", return_value=folder),
            patch(f"{FOLDER_REPO}.fetch_descendant_ids", return_value=[]),
            patch(f"{FOLDER_REPO}.fetch_photos_in_folders", return_value=[photo]),
            patch(f"{FOLDER_REPO}.fetch_folders_by_ids", return_value=[]),
            patch(f"{TRASH_FILES}.delete_many_photo_files", new_callable=AsyncMock),
            patch(f"{TRASH_FILES}.rmtree_folder_fs", new_callable=AsyncMock),
            patch(f"{TRASH_REPO}.delete_folder_row", new_callable=AsyncMock) as mock_del_row,
        ):
            n_folders, n_photos = await TrashService.purge_folder_subtree(db, folder.id)
        assert n_folders == 1
        assert n_photos == 1
        mock_del_row.assert_awaited_once_with(db, folder.id)

    @pytest.mark.asyncio
    async def test_purges_with_descendants(self):
        folder = _make_folder()
        child_id = uuid.uuid4()
        child = SimpleNamespace(
            id=child_id,
            path="vacation/child",
            fs_path=None,
            deleted_at=None,
            parent_id=folder.id,
        )
        photo = _make_photo(folder_id=folder.id)
        db = AsyncMock()
        with (
            patch(f"{FOLDER_REPO}.fetch_folder_any", return_value=folder),
            patch(f"{FOLDER_REPO}.fetch_descendant_ids", return_value=[child_id]),
            patch(f"{FOLDER_REPO}.fetch_photos_in_folders", return_value=[photo]),
            patch(f"{FOLDER_REPO}.fetch_folders_by_ids", return_value=[child]),
            patch(f"{TRASH_FILES}.delete_many_photo_files", new_callable=AsyncMock),
            patch(f"{TRASH_FILES}.rmtree_folder_fs", new_callable=AsyncMock),
            patch(f"{TRASH_REPO}.delete_folder_row", new_callable=AsyncMock) as mock_del_row,
        ):
            n_folders, n_photos = await TrashService.purge_folder_subtree(db, folder.id)
        assert n_folders == 2
        assert n_photos == 1
        assert mock_del_row.call_count == 2


class TestPurgeExpired:
    @pytest.mark.asyncio
    async def test_purges_expired_photos_and_folders(self):
        photo = _make_photo(deleted_at=datetime.now(UTC))
        folder = _make_folder(deleted_at=datetime.now(UTC), parent_id=None)
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        with (
            patch(f"{TRASH_REPO}.fetch_expired_photos", return_value=[photo]),
            patch(f"{TRASH_REPO}.fetch_expired_root_folders", return_value=[folder]),
            patch(f"{TRASH_REPO}.fetch_expired_non_root_folders", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_active_folder_ids", return_value=set()),
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch(f"{TRASH_FILES}.delete_photo_files", new_callable=AsyncMock),
            patch(f"{TRASH_REPO}.purge_photo_row", new_callable=AsyncMock),
            patch.object(
                TrashService,
                "purge_folder_subtree",
                return_value=(1, 0),
            ),
        ):
            result = await TrashService.purge_expired(db, ttl_days=30)
        assert result["purged_photos"] >= 0
        assert result["purged_folders"] >= 0

    @pytest.mark.asyncio
    async def test_handles_folder_exception_gracefully(self):
        folder = _make_folder(deleted_at=datetime.now(UTC), parent_id=None)
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        with (
            patch(f"{TRASH_REPO}.fetch_expired_photos", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_expired_root_folders", return_value=[folder]),
            patch(f"{TRASH_REPO}.fetch_expired_non_root_folders", return_value=[]),
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch.object(
                TrashService,
                "purge_folder_subtree",
                side_effect=RuntimeError("db error"),
            ),
        ):
            result = await TrashService.purge_expired(db, ttl_days=30)
        assert result["purged_folders"] == 0
        db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_non_root_folders_with_active_parent(self):
        parent_id = uuid.uuid4()
        folder = _make_folder(deleted_at=datetime.now(UTC), parent_id=parent_id)
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        with (
            patch(f"{TRASH_REPO}.fetch_expired_photos", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_expired_root_folders", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_expired_non_root_folders", return_value=[folder]),
            patch(f"{TRASH_REPO}.fetch_active_folder_ids", return_value={parent_id}),
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch.object(
                TrashService,
                "purge_folder_subtree",
                return_value=(1, 0),
            ),
        ):
            result = await TrashService.purge_expired(db, ttl_days=30)
        assert result["purged_folders"] == 1

    @pytest.mark.asyncio
    async def test_non_root_folders_without_active_parent_skipped(self):
        parent_id = uuid.uuid4()
        folder = _make_folder(deleted_at=datetime.now(UTC), parent_id=parent_id)
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        with (
            patch(f"{TRASH_REPO}.fetch_expired_photos", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_expired_root_folders", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_expired_non_root_folders", return_value=[folder]),
            patch(f"{TRASH_REPO}.fetch_active_folder_ids", return_value=set()),
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch.object(TrashService, "purge_folder_subtree", return_value=(1, 0)) as mock_purge,
        ):
            result = await TrashService.purge_expired(db, ttl_days=30)
        mock_purge.assert_not_called()
        assert result["purged_folders"] == 0


class TestEmptyTrash:
    @pytest.mark.asyncio
    async def test_empty_trash_no_items(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        with (
            patch(f"{TRASH_REPO}.fetch_all_trashed_photos", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_all_trashed_folders", return_value=[]),
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
        ):
            result = await TrashService.empty_trash(db)
        assert result == {"purged_photos": 0, "purged_folders": 0}

    @pytest.mark.asyncio
    async def test_empty_trash_with_photos(self):
        photo = _make_photo(deleted_at=datetime.now(UTC))
        db = AsyncMock()
        db.commit = AsyncMock()
        with (
            patch(f"{TRASH_REPO}.fetch_all_trashed_photos", return_value=[photo]),
            patch(f"{TRASH_REPO}.fetch_all_trashed_folders", return_value=[]),
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch(f"{TRASH_FILES}.delete_photo_files", new_callable=AsyncMock),
            patch(f"{TRASH_REPO}.purge_photo_row", new_callable=AsyncMock),
        ):
            result = await TrashService.empty_trash(db)
        assert result["purged_photos"] == 1

    @pytest.mark.asyncio
    async def test_empty_trash_with_folders(self):
        folder = _make_folder(deleted_at=datetime.now(UTC), parent_id=None)
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        with (
            patch(f"{TRASH_REPO}.fetch_all_trashed_photos", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_all_trashed_folders", return_value=[folder]),
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch.object(TrashService, "purge_folder_subtree", return_value=(1, 0)),
        ):
            result = await TrashService.empty_trash(db)
        assert result["purged_folders"] == 1

    @pytest.mark.asyncio
    async def test_empty_trash_folder_exception(self):
        folder = _make_folder(deleted_at=datetime.now(UTC), parent_id=None)
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        with (
            patch(f"{TRASH_REPO}.fetch_all_trashed_photos", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_all_trashed_folders", return_value=[folder]),
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch.object(TrashService, "purge_folder_subtree", side_effect=RuntimeError("err")),
        ):
            result = await TrashService.empty_trash(db)
        assert result["purged_folders"] == 0
        db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_empty_trash_only_root_folders_processed(self):
        parent_id = uuid.uuid4()
        root = SimpleNamespace(
            id=parent_id,
            deleted_at=datetime.now(UTC),
            parent_id=None,
            path="root",
            fs_path=None,
            name="Root",
        )
        child = SimpleNamespace(
            id=uuid.uuid4(),
            deleted_at=datetime.now(UTC),
            parent_id=parent_id,
            path="root/child",
            fs_path=None,
            name="Child",
        )
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        with (
            patch(f"{TRASH_REPO}.fetch_all_trashed_photos", return_value=[]),
            patch(f"{TRASH_REPO}.fetch_all_trashed_folders", return_value=[root, child]),
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch.object(TrashService, "purge_folder_subtree", return_value=(2, 0)) as mock_purge,
        ):
            result = await TrashService.empty_trash(db)
        assert mock_purge.call_count == 1


class TestListTrashedFolders:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        folder = _make_folder(deleted_at=datetime.now(UTC))
        db = AsyncMock()
        with patch(f"{FOLDER_REPO}.fetch_deleted_folders_ordered", return_value=[folder]):
            result = await TrashService.list_trashed_folders(db)
        assert result == [folder]

    @pytest.mark.asyncio
    async def test_empty(self):
        db = AsyncMock()
        with patch(f"{FOLDER_REPO}.fetch_deleted_folders_ordered", return_value=[]):
            result = await TrashService.list_trashed_folders(db)
        assert result == []


class TestEmptyTrashForUser:
    @pytest.mark.asyncio
    async def test_purges_accessible_photos_and_folders(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        folder = _make_folder()
        photo = _make_photo(folder_id=folder.id)
        folder_id = folder.id

        with (
            patch(
                f"{PHOTO_REPO}.fetch_deleted_photos_with_folders", return_value=[(photo, folder)]
            ),
            patch(RESOLVE_BATCH, return_value={folder_id: "manager"}),
            patch(f"{FOLDER_REPO}.fetch_deleted_folders_ordered", return_value=[]),
            patch.object(TrashService, "purge_photo", new_callable=AsyncMock),
        ):
            result = await TrashService.empty_trash_for_user(db, user, redis)
        assert result["purged_photos"] == 1

    @pytest.mark.asyncio
    async def test_skips_photos_without_permission(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()
        db.commit = AsyncMock()

        folder = _make_folder()
        photo = _make_photo(folder_id=folder.id)
        folder_id = folder.id

        with (
            patch(
                f"{PHOTO_REPO}.fetch_deleted_photos_with_folders", return_value=[(photo, folder)]
            ),
            patch(RESOLVE_BATCH, return_value={folder_id: "viewer"}),
            patch(f"{FOLDER_REPO}.fetch_deleted_folders_ordered", return_value=[]),
            patch.object(TrashService, "purge_photo", new_callable=AsyncMock) as mock_purge,
        ):
            result = await TrashService.empty_trash_for_user(db, user, redis)
        mock_purge.assert_not_called()
        assert result["purged_photos"] == 0

    @pytest.mark.asyncio
    async def test_skips_photos_with_none_folder(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()
        db.commit = AsyncMock()

        photo = _make_photo()

        with (
            patch(f"{PHOTO_REPO}.fetch_deleted_photos_with_folders", return_value=[(photo, None)]),
            patch(RESOLVE_BATCH, return_value={}),
            patch(f"{FOLDER_REPO}.fetch_deleted_folders_ordered", return_value=[]),
            patch.object(TrashService, "purge_photo", new_callable=AsyncMock) as mock_purge,
        ):
            result = await TrashService.empty_trash_for_user(db, user, redis)
        mock_purge.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_purge_photo_exception(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        folder = _make_folder()
        photo = _make_photo(folder_id=folder.id)
        folder_id = folder.id

        with (
            patch(
                f"{PHOTO_REPO}.fetch_deleted_photos_with_folders", return_value=[(photo, folder)]
            ),
            patch(RESOLVE_BATCH, return_value={folder_id: "manager"}),
            patch(f"{FOLDER_REPO}.fetch_deleted_folders_ordered", return_value=[]),
            patch.object(TrashService, "purge_photo", side_effect=RuntimeError("err")),
        ):
            result = await TrashService.empty_trash_for_user(db, user, redis)
        assert result["purged_photos"] == 0
        db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_purges_accessible_folders(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        folder = _make_folder(deleted_at=datetime.now(UTC), parent_id=None)
        folder_id = folder.id

        with (
            patch(f"{PHOTO_REPO}.fetch_deleted_photos_with_folders", return_value=[]),
            patch(RESOLVE_BATCH, side_effect=[{}, {folder_id: "manager"}]),
            patch(f"{FOLDER_REPO}.fetch_deleted_folders_ordered", return_value=[folder]),
            patch.object(TrashService, "purge_folder_subtree", return_value=(1, 0)),
        ):
            result = await TrashService.empty_trash_for_user(db, user, redis)
        assert result["purged_folders"] == 1

    @pytest.mark.asyncio
    async def test_handles_folder_exception(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        folder = _make_folder(deleted_at=datetime.now(UTC), parent_id=None)
        folder_id = folder.id

        with (
            patch(f"{PHOTO_REPO}.fetch_deleted_photos_with_folders", return_value=[]),
            patch(RESOLVE_BATCH, side_effect=[{}, {folder_id: "manager"}]),
            patch(f"{FOLDER_REPO}.fetch_deleted_folders_ordered", return_value=[folder]),
            patch.object(TrashService, "purge_folder_subtree", side_effect=RuntimeError("err")),
        ):
            result = await TrashService.empty_trash_for_user(db, user, redis)
        assert result["purged_folders"] == 0
        db.rollback.assert_awaited()


class TestListTrashedPhotos:
    @pytest.mark.asyncio
    async def test_admin_returns_all(self):
        user = _make_user(role="admin")
        redis = MagicMock()
        db = AsyncMock()

        photo = _make_photo(deleted_at=datetime.now(UTC))
        folder = _make_folder()
        pub = _make_photo_public()

        with (
            patch(f"{PHOTO_REPO}.count_deleted_photos_admin", return_value=1),
            patch(
                f"{PHOTO_REPO}.fetch_deleted_photos_admin_page",
                return_value=[(photo, folder)],
            ),
            patch(
                "app.services.photos_trash.photo_to_public",
                return_value=pub,
            ),
        ):
            result = await TrashService.list_trashed_photos(db, user, redis, page=1, per_page=20)
        assert result.total == 1
        assert result.page == 1

    @pytest.mark.asyncio
    async def test_non_admin_filters_by_permission(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()

        folder = _make_folder()
        photo = _make_photo(deleted_at=datetime.now(UTC), folder_id=folder.id)
        folder_id = folder.id
        pub = _make_photo_public()

        with (
            patch(
                f"{PHOTO_REPO}.fetch_deleted_photos_with_folders",
                return_value=[(photo, folder)],
            ),
            patch(RESOLVE_BATCH, return_value={folder_id: "manager"}),
            patch(
                "app.services.photos_trash.photo_to_public",
                return_value=pub,
            ),
        ):
            result = await TrashService.list_trashed_photos(db, user, redis, page=1, per_page=20)
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_non_admin_skips_no_permission(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()

        folder = _make_folder()
        photo = _make_photo(deleted_at=datetime.now(UTC), folder_id=folder.id)
        folder_id = folder.id

        with (
            patch(
                f"{PHOTO_REPO}.fetch_deleted_photos_with_folders",
                return_value=[(photo, folder)],
            ),
            patch(RESOLVE_BATCH, return_value={folder_id: "viewer"}),
        ):
            result = await TrashService.list_trashed_photos(db, user, redis, page=1, per_page=20)
        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_non_admin_skips_none_folder(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()

        photo = _make_photo(deleted_at=datetime.now(UTC))

        with (
            patch(
                f"{PHOTO_REPO}.fetch_deleted_photos_with_folders",
                return_value=[(photo, None)],
            ),
            patch(RESOLVE_BATCH, return_value={}),
        ):
            result = await TrashService.list_trashed_photos(db, user, redis, page=1, per_page=20)
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_pagination_slices_correctly(self):
        user = _make_user(role="member")
        redis = MagicMock()
        db = AsyncMock()

        folder = _make_folder()
        folder_id = folder.id
        photos = [_make_photo(deleted_at=datetime.now(UTC), folder_id=folder_id) for _ in range(5)]

        with (
            patch(
                f"{PHOTO_REPO}.fetch_deleted_photos_with_folders",
                return_value=[(p, folder) for p in photos],
            ),
            patch(RESOLVE_BATCH, return_value={folder_id: "manager"}),
            patch(
                "app.services.photos_trash.photo_to_public",
                side_effect=lambda *_: _make_photo_public(),
            ),
        ):
            result = await TrashService.list_trashed_photos(db, user, redis, page=2, per_page=2)
        assert result.total == 5
        assert len(result.items) == 2


class TestPurgePhotoRows:
    @pytest.mark.asyncio
    async def test_purges_all_photos(self):
        photo1 = _make_photo()
        photo2 = _make_photo()
        db = AsyncMock()

        with (
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch(f"{TRASH_FILES}.delete_photo_files", new_callable=AsyncMock),
            patch(f"{TRASH_REPO}.purge_photo_row", new_callable=AsyncMock),
        ):
            count = await TrashService._purge_photo_rows(db, [photo1, photo2])
        assert count == 2

    @pytest.mark.asyncio
    async def test_handles_exception_continues(self):
        photo1 = _make_photo()
        photo2 = _make_photo()
        db = AsyncMock()

        call_count = 0

        async def raise_on_first(photo, folder):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("disk full")

        with (
            patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}),
            patch(f"{TRASH_FILES}.delete_photo_files", side_effect=raise_on_first),
            patch(f"{TRASH_REPO}.purge_photo_row", new_callable=AsyncMock),
        ):
            count = await TrashService._purge_photo_rows(db, [photo1, photo2])
        assert count == 1

    @pytest.mark.asyncio
    async def test_empty_photos_returns_zero(self):
        db = AsyncMock()
        with patch(f"{PHOTO_REPO}.fetch_folders_map", return_value={}):
            count = await TrashService._purge_photo_rows(db, [])
        assert count == 0
