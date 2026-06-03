"""Characterization tests for app/api/photos/folders.py (FO-0).

Raises coverage from ~22% toward >=75% without touching production code.
One test class per route; all tests use authed_client_factory + patch to mock
the repo/service/acl layers so no real DB or Redis is required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

BASE = "/api/v1/photos/folders"


def _make_folder_public(
    *,
    folder_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    name: str = "Test Folder",
    slug: str = "test-folder",
    path: str = "test-folder",
    permission: str = "manager",
) -> dict:
    from app.schemas.photos import FolderPublic

    now = datetime.now(UTC)
    return FolderPublic(
        id=folder_id or uuid.uuid4(),
        parent_id=parent_id,
        name=name,
        slug=slug,
        path=path,
        description=None,
        cover_photo_id=None,
        photos_count=0,
        children_count=0,
        permission=permission,
        created_at=now,
        updated_at=now,
    )


def _make_folder_mock(
    *,
    folder_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    name: str = "Test Folder",
    slug: str = "test-folder",
    path: str = "test-folder",
    fs_path: str = "Test Folder",
    description: str | None = None,
    cover_photo_id: uuid.UUID | None = None,
    deleted_at: datetime | None = None,
    created_by: uuid.UUID | None = None,
) -> MagicMock:
    f = MagicMock()
    f.id = folder_id or uuid.uuid4()
    f.parent_id = parent_id
    f.name = name
    f.slug = slug
    f.path = path
    f.fs_path = fs_path
    f.description = description
    f.cover_photo_id = cover_photo_id
    f.deleted_at = deleted_at
    f.created_by = created_by or uuid.uuid4()
    f.created_at = datetime.now(UTC)
    f.updated_at = datetime.now(UTC)
    return f


_AUDIT_PATCH = "app.services.audit.push_audit_event"
_INVALIDATE_PATCH = "app.api.photos.folders.invalidate_folder_cache"
_FOLDER_TO_PUBLIC_PATCH = "app.api.photos.folders._folder_to_public"
_REQUIRE_PERM_PATCH = "app.api.photos.folders.require_folder_permission"
_RESOLVE_PERM_PATCH = "app.api.photos.folders.resolve_folder_permission"
_FILTER_ACCESSIBLE_PATCH = "app.api.photos.folders.filter_accessible_folders_with_perm"
_PERM_GTE_PATCH = "app.api.photos.folders.perm_gte"
_REPO = "app.api.photos.folders.folder_repo"
_TRASH_PATCH = "app.api.photos.folders.TrashService"
_FOLDER_SVC_PATCH = "app.api.photos.folders.folder_service"
_STORAGE_PATCH = "app.api.photos.folders.photos_storage"


class TestListFolderTree:
    async def test_empty_tree_returns_items(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        with (
            patch(f"{_REPO}.fetch_active_folders_ordered", new=AsyncMock(return_value=[])),
            patch(_FILTER_ACCESSIBLE_PATCH, new=AsyncMock(return_value=[])),
        ):
            r = await ac.get(f"{BASE}/tree")
        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_admin_sees_all_folders(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, name="Root", slug="root", path="root")
        with (
            patch(f"{_REPO}.fetch_active_folders_ordered", new=AsyncMock(return_value=[folder])),
            patch(
                _FILTER_ACCESSIBLE_PATCH,
                new=AsyncMock(return_value=[(folder, "manager")]),
            ),
        ):
            r = await ac.get(f"{BASE}/tree")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(fid)
        assert items[0]["permission"] == "manager"

    async def test_nested_folder_appears_under_parent(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        parent = _make_folder_mock(
            folder_id=parent_id, name="Parent", slug="parent", path="parent", parent_id=None
        )
        child = _make_folder_mock(
            folder_id=child_id,
            name="Child",
            slug="child",
            path="parent/child",
            parent_id=parent_id,
        )
        with (
            patch(
                f"{_REPO}.fetch_active_folders_ordered",
                new=AsyncMock(return_value=[parent, child]),
            ),
            patch(
                _FILTER_ACCESSIBLE_PATCH,
                new=AsyncMock(return_value=[(parent, "viewer"), (child, "viewer")]),
            ),
        ):
            r = await ac.get(f"{BASE}/tree")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(parent_id)
        assert len(items[0]["children"]) == 1
        assert items[0]["children"][0]["id"] == str(child_id)

    async def test_orphan_child_becomes_root(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        orphan_parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        child = _make_folder_mock(
            folder_id=child_id,
            name="Child",
            slug="child",
            path="parent/child",
            parent_id=orphan_parent_id,
        )
        with (
            patch(
                f"{_REPO}.fetch_active_folders_ordered",
                new=AsyncMock(return_value=[child]),
            ),
            patch(
                _FILTER_ACCESSIBLE_PATCH,
                new=AsyncMock(return_value=[(child, "viewer")]),
            ),
        ):
            r = await ac.get(f"{BASE}/tree")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(child_id)


class TestListDeletedFolders:
    async def test_admin_sees_all_trashed_as_manager(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=datetime.now(UTC))
        pub = _make_folder_public(folder_id=fid, permission="manager")
        with (
            patch(f"{_TRASH_PATCH}.list_trashed_folders", new=AsyncMock(return_value=[folder])),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.get(f"{BASE}/deleted")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == str(fid)
        assert data[0]["permission"] == "manager"

    async def test_non_admin_filters_by_manager_perm(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=datetime.now(UTC), parent_id=None)
        pub = _make_folder_public(folder_id=fid, permission="manager")
        with (
            patch(f"{_TRASH_PATCH}.list_trashed_folders", new=AsyncMock(return_value=[folder])),
            patch(_RESOLVE_PERM_PATCH, new=AsyncMock(return_value="manager")),
            patch(_PERM_GTE_PATCH, return_value=True),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.get(f"{BASE}/deleted")
        assert r.status_code == 200
        assert len(r.json()) == 1

    async def test_non_admin_hides_folders_without_manager_perm(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=datetime.now(UTC), parent_id=None)
        with (
            patch(f"{_TRASH_PATCH}.list_trashed_folders", new=AsyncMock(return_value=[folder])),
            patch(_RESOLVE_PERM_PATCH, new=AsyncMock(return_value="viewer")),
            patch(_PERM_GTE_PATCH, return_value=False),
        ):
            r = await ac.get(f"{BASE}/deleted")
        assert r.status_code == 200
        assert r.json() == []

    async def test_non_admin_skips_nested_deleted_folders(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        parent = _make_folder_mock(
            folder_id=parent_id, deleted_at=datetime.now(UTC), parent_id=None
        )
        child = _make_folder_mock(
            folder_id=child_id, deleted_at=datetime.now(UTC), parent_id=parent_id
        )
        pub = _make_folder_public(folder_id=parent_id, permission="manager")
        with (
            patch(
                f"{_TRASH_PATCH}.list_trashed_folders",
                new=AsyncMock(return_value=[parent, child]),
            ),
            patch(_RESOLVE_PERM_PATCH, new=AsyncMock(return_value="manager")),
            patch(_PERM_GTE_PATCH, return_value=True),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.get(f"{BASE}/deleted")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["id"] == str(parent_id)

    async def test_empty_trash(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with patch(f"{_TRASH_PATCH}.list_trashed_folders", new=AsyncMock(return_value=[])):
            r = await ac.get(f"{BASE}/deleted")
        assert r.status_code == 200
        assert r.json() == []


class TestGetFolder:
    async def test_404_when_not_found(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        fid = uuid.uuid4()
        with patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=None)):
            r = await ac.get(f"{BASE}/{fid}")
        assert r.status_code == 404

    async def test_403_when_no_permission(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid)
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_RESOLVE_PERM_PATCH, new=AsyncMock(return_value=None)),
        ):
            r = await ac.get(f"{BASE}/{fid}")
        assert r.status_code == 403

    async def test_200_with_counts(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid)
        pub = _make_folder_public(folder_id=fid, permission="viewer")
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_RESOLVE_PERM_PATCH, new=AsyncMock(return_value="viewer")),
            patch(f"{_REPO}.count_active_photos_in_folder", new=AsyncMock(return_value=5)),
            patch(f"{_REPO}.count_active_subfolders", new=AsyncMock(return_value=2)),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.get(f"{BASE}/{fid}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == str(fid)


class TestCreateFolder:
    async def test_non_admin_editor_cannot_create_root(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.post(BASE, json={"name": "My Folder"})
        assert r.status_code == 403

    async def test_editor_can_create_root_folder(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")
        fid = uuid.uuid4()
        pub = _make_folder_public(folder_id=fid, name="My Folder", permission="manager")

        path_mock = MagicMock()
        path_mock.mkdir = MagicMock()

        with (
            patch(
                f"{_FOLDER_SVC_PATCH}.resolve_unique_slug", new=AsyncMock(return_value="my-folder")
            ),
            patch(
                f"{_FOLDER_SVC_PATCH}.resolve_unique_fs_seg",
                new=AsyncMock(return_value="My Folder"),
            ),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
            patch(_AUDIT_PATCH, new=AsyncMock()),
            patch(f"{_STORAGE_PATCH}.folder_fs_path", return_value=path_mock),
        ):
            r = await ac.post(BASE, json={"name": "My Folder"})
        assert r.status_code == 201

    async def test_admin_can_create_root_folder(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        pub = _make_folder_public(folder_id=fid, name="Admin Root", permission="manager")

        path_mock = MagicMock()
        path_mock.mkdir = MagicMock()

        with (
            patch(
                f"{_FOLDER_SVC_PATCH}.resolve_unique_slug", new=AsyncMock(return_value="admin-root")
            ),
            patch(
                f"{_FOLDER_SVC_PATCH}.resolve_unique_fs_seg",
                new=AsyncMock(return_value="Admin Root"),
            ),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
            patch(_AUDIT_PATCH, new=AsyncMock()),
            patch(f"{_STORAGE_PATCH}.folder_fs_path", return_value=path_mock),
        ):
            r = await ac.post(BASE, json={"name": "Admin Root"})
        assert r.status_code == 201

    async def test_404_when_parent_not_found(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        missing_parent_id = uuid.uuid4()
        with patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=None)):
            r = await ac.post(BASE, json={"name": "Child", "parent_id": str(missing_parent_id)})
        assert r.status_code == 404

    async def test_create_subfolder_success(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        parent_id = uuid.uuid4()
        parent = _make_folder_mock(
            folder_id=parent_id, path="parent", fs_path="Parent", slug="parent"
        )
        fid = uuid.uuid4()
        pub = _make_folder_public(
            folder_id=fid, parent_id=parent_id, path="parent/child", permission="manager"
        )
        path_mock = MagicMock()
        path_mock.mkdir = MagicMock()
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=parent)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_FOLDER_SVC_PATCH}.resolve_unique_slug", new=AsyncMock(return_value="child")),
            patch(
                f"{_FOLDER_SVC_PATCH}.resolve_unique_fs_seg",
                new=AsyncMock(return_value="child"),
            ),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
            patch(_AUDIT_PATCH, new=AsyncMock()),
            patch(f"{_STORAGE_PATCH}.folder_fs_path", return_value=path_mock),
        ):
            r = await ac.post(BASE, json={"name": "child", "parent_id": str(parent_id)})
        assert r.status_code == 201

    async def test_409_on_integrity_error(self, authed_client_factory, app):
        from app.api.deps import get_db

        ac, _ = authed_client_factory(role="admin")

        async def _db_with_integrity_error():
            session = MagicMock()
            session.add = MagicMock()
            session.commit = AsyncMock(side_effect=IntegrityError("dup", None, Exception("unique")))
            session.rollback = AsyncMock()
            session.refresh = AsyncMock()
            yield session

        app.dependency_overrides[get_db] = _db_with_integrity_error

        path_mock = MagicMock()
        path_mock.mkdir = MagicMock()
        try:
            with (
                patch(
                    f"{_FOLDER_SVC_PATCH}.resolve_unique_slug",
                    new=AsyncMock(return_value="my-folder"),
                ),
                patch(
                    f"{_FOLDER_SVC_PATCH}.resolve_unique_fs_seg",
                    new=AsyncMock(return_value="My Folder"),
                ),
                patch(f"{_STORAGE_PATCH}.folder_fs_path", return_value=path_mock),
            ):
                r = await ac.post(BASE, json={"name": "My Folder"})
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 409

    async def test_mkdir_failure_does_not_fail_request(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        pub = _make_folder_public(folder_id=fid, name="Folder", permission="manager")

        bad_path = MagicMock()
        bad_path.mkdir = MagicMock(side_effect=OSError("disk full"))

        with (
            patch(f"{_FOLDER_SVC_PATCH}.resolve_unique_slug", new=AsyncMock(return_value="folder")),
            patch(
                f"{_FOLDER_SVC_PATCH}.resolve_unique_fs_seg",
                new=AsyncMock(return_value="folder"),
            ),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
            patch(_AUDIT_PATCH, new=AsyncMock()),
            patch(f"{_STORAGE_PATCH}.folder_fs_path", return_value=bad_path),
        ):
            r = await ac.post(BASE, json={"name": "Folder"})
        assert r.status_code == 201

    async def test_audit_event_emitted_on_create(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        pub = _make_folder_public(folder_id=fid, name="Audited", permission="manager")
        path_mock = MagicMock()
        path_mock.mkdir = MagicMock()
        audit_mock = AsyncMock()
        with (
            patch(
                f"{_FOLDER_SVC_PATCH}.resolve_unique_slug", new=AsyncMock(return_value="audited")
            ),
            patch(
                f"{_FOLDER_SVC_PATCH}.resolve_unique_fs_seg",
                new=AsyncMock(return_value="Audited"),
            ),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
            patch(_AUDIT_PATCH, audit_mock),
            patch(f"{_STORAGE_PATCH}.folder_fs_path", return_value=path_mock),
        ):
            r = await ac.post(BASE, json={"name": "Audited"})
        assert r.status_code == 201
        audit_mock.assert_called_once()
        call_kwargs = audit_mock.call_args
        assert call_kwargs.kwargs.get("event_type") == "photos.folder_created"


class TestUpdateFolder:
    async def test_404_when_not_found(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        with patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=None)):
            r = await ac.patch(f"{BASE}/{fid}", json={"name": "New Name"})
        assert r.status_code == 404

    async def test_update_description_success(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid)
        pub = _make_folder_public(folder_id=fid, permission="manager")
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_FOLDER_SVC_PATCH}.commit_with_fs_rename", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.patch(f"{BASE}/{fid}", json={"description": "New desc"})
        assert r.status_code == 200

    async def test_update_name_calls_apply_rename(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, name="Old Name")
        pub = _make_folder_public(folder_id=fid, name="New Name", permission="manager")
        rename_mock = AsyncMock()
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_FOLDER_SVC_PATCH}.apply_folder_rename", rename_mock),
            patch(f"{_FOLDER_SVC_PATCH}.commit_with_fs_rename", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.patch(f"{BASE}/{fid}", json={"name": "New Name"})
        assert r.status_code == 200
        rename_mock.assert_called_once()

    async def test_update_parent_calls_apply_move(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        new_parent_id = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, parent_id=None)
        pub = _make_folder_public(folder_id=fid, parent_id=new_parent_id, permission="manager")
        move_mock = AsyncMock()
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_FOLDER_SVC_PATCH}.apply_folder_move", move_mock),
            patch(f"{_FOLDER_SVC_PATCH}.commit_with_fs_rename", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.patch(f"{BASE}/{fid}", json={"parent_id": str(new_parent_id)})
        assert r.status_code == 200
        move_mock.assert_called_once()

    async def test_update_cover_photo_calls_apply_cover(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        photo_id = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, cover_photo_id=None)
        pub = _make_folder_public(folder_id=fid, permission="manager")
        cover_mock = AsyncMock()
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_FOLDER_SVC_PATCH}.apply_cover_photo", cover_mock),
            patch(f"{_FOLDER_SVC_PATCH}.commit_with_fs_rename", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.patch(f"{BASE}/{fid}", json={"cover_photo_id": str(photo_id)})
        assert r.status_code == 200
        cover_mock.assert_called_once()

    async def test_cache_invalidated_after_update(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid)
        pub = _make_folder_public(folder_id=fid, permission="manager")
        invalidate_mock = AsyncMock()
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_FOLDER_SVC_PATCH}.commit_with_fs_rename", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, invalidate_mock),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.patch(f"{BASE}/{fid}", json={"description": "x"})
        assert r.status_code == 200
        invalidate_mock.assert_called_once()

    async def test_403_when_insufficient_permission(self, authed_client_factory):
        from fastapi import HTTPException

        ac, _ = authed_client_factory(role="reader")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid)
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(
                _REQUIRE_PERM_PATCH,
                new=AsyncMock(side_effect=HTTPException(status_code=403, detail="No access")),
            ),
        ):
            r = await ac.patch(f"{BASE}/{fid}", json={"description": "x"})
        assert r.status_code == 403


class TestDeleteFolder:
    async def test_404_when_not_found(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        with patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=None)):
            r = await ac.delete(f"{BASE}/{fid}")
        assert r.status_code == 404

    async def test_204_on_success(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid)
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_TRASH_PATCH}.soft_delete_folder", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_AUDIT_PATCH, new=AsyncMock()),
        ):
            r = await ac.delete(f"{BASE}/{fid}")
        assert r.status_code == 204

    async def test_audit_event_type_on_delete(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid)
        audit_mock = AsyncMock()
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_TRASH_PATCH}.soft_delete_folder", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_AUDIT_PATCH, audit_mock),
        ):
            r = await ac.delete(f"{BASE}/{fid}")
        assert r.status_code == 204
        audit_mock.assert_called_once()
        assert audit_mock.call_args.kwargs.get("event_type") == "photos.folder_deleted"

    async def test_cache_invalidated_on_delete(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid)
        invalidate_mock = AsyncMock()
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_TRASH_PATCH}.soft_delete_folder", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, invalidate_mock),
            patch(_AUDIT_PATCH, new=AsyncMock()),
        ):
            r = await ac.delete(f"{BASE}/{fid}")
        assert r.status_code == 204
        invalidate_mock.assert_called_once()

    async def test_403_when_insufficient_permission(self, authed_client_factory):
        from fastapi import HTTPException

        ac, _ = authed_client_factory(role="reader")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid)
        with (
            patch(f"{_REPO}.fetch_active_folder", new=AsyncMock(return_value=folder)),
            patch(
                _REQUIRE_PERM_PATCH,
                new=AsyncMock(side_effect=HTTPException(status_code=403, detail="No access")),
            ),
        ):
            r = await ac.delete(f"{BASE}/{fid}")
        assert r.status_code == 403


class TestRestoreFolder:
    async def test_404_when_not_found(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        with patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=None)):
            r = await ac.post(f"{BASE}/{fid}/restore")
        assert r.status_code == 404

    async def test_400_when_not_deleted(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=None)
        with (
            patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=folder)),
        ):
            r = await ac.post(f"{BASE}/{fid}/restore")
        assert r.status_code == 400

    async def test_200_on_success(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=datetime.now(UTC))
        pub = _make_folder_public(folder_id=fid, permission="manager")
        with (
            patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_TRASH_PATCH}.restore_folder", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_AUDIT_PATCH, new=AsyncMock()),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.post(f"{BASE}/{fid}/restore")
        assert r.status_code == 200
        assert r.json()["id"] == str(fid)

    async def test_audit_event_type_on_restore(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=datetime.now(UTC))
        pub = _make_folder_public(folder_id=fid, permission="manager")
        audit_mock = AsyncMock()
        with (
            patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_TRASH_PATCH}.restore_folder", new=AsyncMock()),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_AUDIT_PATCH, audit_mock),
            patch(_FOLDER_TO_PUBLIC_PATCH, return_value=pub),
        ):
            r = await ac.post(f"{BASE}/{fid}/restore")
        assert r.status_code == 200
        audit_mock.assert_called_once()
        assert audit_mock.call_args.kwargs.get("event_type") == "photos.folder_restored"

    async def test_403_when_no_permission(self, authed_client_factory):
        from fastapi import HTTPException

        ac, _ = authed_client_factory(role="reader")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=datetime.now(UTC))
        with (
            patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=folder)),
            patch(
                _REQUIRE_PERM_PATCH,
                new=AsyncMock(side_effect=HTTPException(status_code=403, detail="No access")),
            ),
        ):
            r = await ac.post(f"{BASE}/{fid}/restore")
        assert r.status_code == 403


class TestPurgeFolder:
    async def test_404_when_not_found(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        with patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=None)):
            r = await ac.delete(f"{BASE}/{fid}/purge")
        assert r.status_code == 404

    async def test_400_when_not_in_trash(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=None)
        with patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=folder)):
            r = await ac.delete(f"{BASE}/{fid}/purge")
        assert r.status_code == 400

    async def test_204_on_success(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=datetime.now(UTC))
        with (
            patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_TRASH_PATCH}.purge_folder_subtree", new=AsyncMock(return_value=(3, 10))),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_AUDIT_PATCH, new=AsyncMock()),
        ):
            r = await ac.delete(f"{BASE}/{fid}/purge")
        assert r.status_code == 204

    async def test_audit_event_type_on_purge(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=datetime.now(UTC))
        audit_mock = AsyncMock()
        with (
            patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=folder)),
            patch(_REQUIRE_PERM_PATCH, new=AsyncMock()),
            patch(f"{_TRASH_PATCH}.purge_folder_subtree", new=AsyncMock(return_value=(3, 10))),
            patch(_INVALIDATE_PATCH, new=AsyncMock()),
            patch(_AUDIT_PATCH, audit_mock),
        ):
            r = await ac.delete(f"{BASE}/{fid}/purge")
        assert r.status_code == 204
        audit_mock.assert_called_once()
        call_kwargs = audit_mock.call_args.kwargs
        assert call_kwargs.get("event_type") == "photos.folder_purged"
        assert call_kwargs["metadata"]["purged_folders"] == 3
        assert call_kwargs["metadata"]["purged_photos"] == 10

    async def test_403_when_insufficient_permission(self, authed_client_factory):
        from fastapi import HTTPException

        ac, _ = authed_client_factory(role="reader")
        fid = uuid.uuid4()
        folder = _make_folder_mock(folder_id=fid, deleted_at=datetime.now(UTC))
        with (
            patch(f"{_REPO}.fetch_folder_any", new=AsyncMock(return_value=folder)),
            patch(
                _REQUIRE_PERM_PATCH,
                new=AsyncMock(side_effect=HTTPException(status_code=403, detail="No access")),
            ),
        ):
            r = await ac.delete(f"{BASE}/{fid}/purge")
        assert r.status_code == 403
