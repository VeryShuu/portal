"""
Test coverage for app/api/files/folders.py

Coverage:
- GET /files/tree: empty tree / with accessible folders / parent_id filter
- GET /files/folders/{id}: 404 / nc error → nc_error=True / success
- POST /files/folders: 201 success / 422 invalid name / 409 duplicate / 502 nc error
- PATCH /files/folders/{id}: success no rename / success rename / nc move error 502
- DELETE /files/folders/{id}: 204 / nc 404 ignored / nc 5xx drift (still 204)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_user(role: str = "editor") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        email=f"{role}@test.local",
        full_name="Test User",
    )


def _make_folder(
    *,
    id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    name: str = "folder1",
    nc_path: str = "PortalFiles/folder1",
    description: str | None = None,
    inherit_permissions: bool = True,
    deleted_at=None,
) -> MagicMock:
    f = MagicMock()
    f.id = id or uuid.uuid4()
    f.parent_id = parent_id
    f.name = name
    f.nc_path = nc_path
    f.description = description
    f.inherit_permissions = inherit_permissions
    f.deleted_at = deleted_at
    f.created_by = uuid.uuid4()
    f.created_at = datetime.now(UTC)
    f.updated_at = datetime.now(UTC)
    return f


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    db.refresh = MagicMock()
    db.expunge = MagicMock()
    db.add_all = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    return AsyncMock()


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis, require_role
    from app.api.files._common import _check_module_enabled
    from app.api.files.folders import router

    _app = FastAPI()
    _app.include_router(router)

    async def _fake_user():
        return user

    async def _fake_db():
        return db

    async def _fake_redis():
        return redis

    _app.dependency_overrides[get_current_user] = _fake_user
    _app.dependency_overrides[get_db] = _fake_db
    _app.dependency_overrides[get_redis] = _fake_redis
    _app.dependency_overrides[_check_module_enabled] = lambda: None
    _app.dependency_overrides[require_role("editor", "admin")] = lambda: None
    return _app


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


async def _post(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, json=json)


async def _patch(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.patch(url, json=json)


async def _delete(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.delete(url)


# ── GET /files/tree ────────────────────────────────────────────────────────────


class TestGetFolderTree:
    @pytest.mark.asyncio
    async def test_returns_empty_tree(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        folders_result = MagicMock()
        folders_result.scalars.return_value.all.return_value = []
        db.execute.return_value = folders_result

        with patch(
            "app.api.files.folders.batch_resolve_folder_permissions",
            new_callable=AsyncMock,
            return_value={},
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/files/tree")

        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    @pytest.mark.asyncio
    async def test_returns_accessible_folders(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        root_id = uuid.uuid4()
        child_id = uuid.uuid4()
        root = _make_folder(id=root_id, name="Root", nc_path="Root")
        child = _make_folder(id=child_id, parent_id=root_id, name="Child", nc_path="Root/Child")

        folders_result = MagicMock()
        folders_result.scalars.return_value.all.return_value = [root, child]
        db.execute.return_value = folders_result

        perm_map = {root_id: "viewer", child_id: "viewer"}

        with patch(
            "app.api.files.folders.batch_resolve_folder_permissions",
            new_callable=AsyncMock,
            return_value=perm_map,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/files/tree")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Root"
        assert len(data["items"][0]["children"]) == 1

    @pytest.mark.asyncio
    async def test_inaccessible_folders_excluded(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        folder1_id = uuid.uuid4()
        folder2_id = uuid.uuid4()
        folder1 = _make_folder(id=folder1_id, name="Public")
        folder2 = _make_folder(id=folder2_id, name="Private")

        folders_result = MagicMock()
        folders_result.scalars.return_value.all.return_value = [folder1, folder2]
        db.execute.return_value = folders_result

        with patch(
            "app.api.files.folders.batch_resolve_folder_permissions",
            new_callable=AsyncMock,
            return_value={folder1_id: "viewer"},
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/files/tree")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Public"


# ── GET /files/folders/{id} ────────────────────────────────────────────────────


class TestGetFolderDetail:
    @pytest.mark.asyncio
    async def test_folder_not_found_404(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/files/folders/{folder_id}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_nc_error_returns_nc_error_true(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        from app.services.nextcloud import NextcloudError

        nc_mock = MagicMock()
        nc_mock.list_folder = AsyncMock(side_effect=NextcloudError("NC down", 503))
        nc_mock.href_to_db_nc_path = MagicMock(return_value=None)

        sub_result = MagicMock()
        sub_result.scalars.return_value.all.return_value = []

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.resolve_folder_permission",
                new_callable=AsyncMock,
                return_value="editor",
            ),
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch(
                "app.api.files.folders._build_breadcrumbs",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.api.files.folders._filter_nc_subfolders_by_acl",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.api.files.folders._enrich_nc_items_with_db",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.api.files.folders._normalize_nc_items", return_value=[]),
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/files/folders/{folder.id}")

        assert resp.status_code == 200
        assert resp.json()["nc_error"] is True

    @pytest.mark.asyncio
    async def test_success_returns_folder_and_items(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        nc_mock = MagicMock()
        nc_mock.list_folder = AsyncMock(return_value=[])

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.resolve_folder_permission",
                new_callable=AsyncMock,
                return_value="manager",
            ),
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch(
                "app.api.files.folders._build_breadcrumbs",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.api.files.folders._filter_nc_subfolders_by_acl",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.api.files.folders._enrich_nc_items_with_db",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.api.files.folders._normalize_nc_items", return_value=[]),
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/files/folders/{folder.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["nc_error"] is False
        assert data["items"] == []


# ── POST /files/folders ────────────────────────────────────────────────────────


class TestCreateFolder:
    @pytest.mark.asyncio
    async def test_create_folder_201(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        db.execute.return_value = existing_result
        db.flush = AsyncMock(return_value=None)
        db.commit = AsyncMock(return_value=None)

        async def _fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.inherit_permissions = True

        db.refresh = _fake_refresh

        nc_mock = MagicMock()
        nc_mock.create_folder = AsyncMock(return_value=None)

        with (
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch("app.api.files.folders.save_folder_perms", new_callable=AsyncMock),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(app, "/files/folders", json={"name": "NewFolder"})

        assert resp.status_code == 201
        # F3: creator's manager permission is materialized as a real row.
        assert db.add.call_count >= 2

    @pytest.mark.asyncio
    async def test_creator_manager_perm_row_materialized(self):
        """F3: при создании папки создателю пишется реальная строка manager."""
        from app.models.files import FileFolder as _FileFolder
        from app.models.files import FileFolderPermission

        user = _make_user(role="editor")
        db = _make_db()
        redis = _make_redis()

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        db.execute.return_value = existing_result
        db.flush = AsyncMock(return_value=None)
        db.commit = AsyncMock(return_value=None)

        new_folder_id = uuid.uuid4()

        async def _fake_refresh(obj):
            obj.inherit_permissions = True

        db.refresh = _fake_refresh

        def _add(obj):
            if isinstance(obj, _FileFolder):
                obj.id = new_folder_id

        db.add.side_effect = _add

        nc_mock = MagicMock()
        nc_mock.create_folder = AsyncMock(return_value=None)

        with (
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch("app.api.files.folders.save_folder_perms", new_callable=AsyncMock) as save_perms,
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(app, "/files/folders", json={"name": "NewFolder"})

        assert resp.status_code == 201
        perms = [
            c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], FileFolderPermission)
        ]
        assert len(perms) == 1
        perm = perms[0]
        assert perm.permission == "manager"
        assert perm.subject_type == "user"
        assert perm.subject_id == str(user.id)
        assert perm.folder_id == new_folder_id
        # And it is mirrored into files-acl.json for restore-after-wipe.
        save_perms.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_name_422(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        resp = await _post(app, "/files/folders", json={"name": "bad/name"})

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_duplicate_folder_409(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()
        existing_folder = _make_folder()

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_folder
        db.execute.return_value = existing_result

        app = _build_app(user, db, redis)
        resp = await _post(app, "/files/folders", json={"name": "folder1"})

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_nc_error_returns_502(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        db.execute.return_value = existing_result
        db.flush = AsyncMock(return_value=None)
        db.rollback = AsyncMock(return_value=None)

        from app.services.nextcloud import NextcloudError

        nc_mock = MagicMock()
        nc_mock.create_folder = AsyncMock(side_effect=NextcloudError("NC down", 503))

        with patch("app.api.files.folders.get_nc_service", return_value=nc_mock):
            app = _build_app(user, db, redis)
            resp = await _post(app, "/files/folders", json={"name": "NewFolder"})

        assert resp.status_code == 502


# ── PATCH /files/folders/{id} ─────────────────────────────────────────────────


class TestUpdateFolder:
    @pytest.mark.asyncio
    async def test_update_description_no_rename(self):
        user = _make_user()
        folder = _make_folder(name="folder1", nc_path="PortalFiles/folder1")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)
        db.refresh = AsyncMock(return_value=None)

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.resolve_folder_permission",
                new_callable=AsyncMock,
                return_value="manager",
            ),
            patch("app.api.files.folders.invalidate_folder_cache", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _patch(
                app, f"/files/folders/{folder.id}", json={"description": "New desc"}
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rename_success(self):
        user = _make_user()
        folder = _make_folder(name="old", nc_path="PortalFiles/old")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)
        db.refresh = AsyncMock(return_value=None)

        nc_mock = MagicMock()
        nc_mock.move = AsyncMock(return_value=None)

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.resolve_folder_permission",
                new_callable=AsyncMock,
                return_value="manager",
            ),
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch("app.api.files.folders.invalidate_folder_cache", new_callable=AsyncMock),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _patch(app, f"/files/folders/{folder.id}", json={"name": "newname"})

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rename_cascades_descendant_paths(self):
        """F1: переименование папки должно каскадно переписать nc_path
        вложенных file_folders / file_items / file_shares."""
        user = _make_user()
        folder = _make_folder(name="old", nc_path="PortalFiles/old")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)
        db.refresh = AsyncMock(return_value=None)

        nc_mock = MagicMock()
        nc_mock.move = AsyncMock(return_value=None)

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.resolve_folder_permission",
                new_callable=AsyncMock,
                return_value="manager",
            ),
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch("app.api.files.folders.invalidate_folder_cache", new_callable=AsyncMock),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _patch(app, f"/files/folders/{folder.id}", json={"name": "newname"})

        assert resp.status_code == 200

        cascade_sql = [
            (str(call.args[0]), call.args[1])
            for call in db.execute.call_args_list
            if len(call.args) == 2 and "substring(nc_path" in str(call.args[0])
        ]
        targeted = {
            table
            for sql, _ in cascade_sql
            for table in ("file_folders", "file_items", "file_shares")
            if f"UPDATE {table}" in sql
        }
        assert targeted == {"file_folders", "file_items", "file_shares"}

        params = cascade_sql[0][1]
        assert params["old_prefix"] == "PortalFiles/old/"
        assert params["new_prefix"] == "PortalFiles/newname/"
        assert params["plen"] == len("PortalFiles/old/")

    @pytest.mark.asyncio
    async def test_description_only_does_not_cascade(self):
        """F1: изменение только описания не должно трогать вложенные пути."""
        user = _make_user()
        folder = _make_folder(name="folder1", nc_path="PortalFiles/folder1")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)
        db.refresh = AsyncMock(return_value=None)

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.resolve_folder_permission",
                new_callable=AsyncMock,
                return_value="manager",
            ),
            patch("app.api.files.folders.invalidate_folder_cache", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _patch(
                app, f"/files/folders/{folder.id}", json={"description": "New desc"}
            )

        assert resp.status_code == 200
        cascade_calls = [
            call for call in db.execute.call_args_list if "substring(nc_path" in str(call.args[0])
        ]
        assert cascade_calls == []

    @pytest.mark.asyncio
    async def test_rename_nc_error_returns_502(self):
        user = _make_user()
        folder = _make_folder(name="old", nc_path="PortalFiles/old")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)

        from app.services.nextcloud import NextcloudError

        nc_mock = MagicMock()
        nc_mock.move = AsyncMock(side_effect=NextcloudError("NC error", 503))

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
        ):
            app = _build_app(user, db, redis)
            resp = await _patch(app, f"/files/folders/{folder.id}", json={"name": "newname"})

        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_folder_not_found_404(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _patch(app, f"/files/folders/{folder_id}", json={"description": "x"})

        assert resp.status_code == 404


# ── DELETE /files/folders/{id} ─────────────────────────────────────────────────


class TestDeleteFolder:
    @pytest.mark.asyncio
    async def test_delete_folder_204(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)

        nc_mock = MagicMock()
        nc_mock.delete = AsyncMock(return_value=None)

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch("app.api.files.folders.invalidate_folder_cache", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.invalidate_file_share_folder_cache",
                new_callable=AsyncMock,
            ),
            patch("app.api.files.folders.drop_folder_perms", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.drop_file_shares_under_prefix",
                new_callable=AsyncMock,
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/files/folders/{folder.id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_nc_404_ignored(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)

        from app.services.nextcloud import NextcloudError

        nc_mock = MagicMock()
        nc_mock.delete = AsyncMock(side_effect=NextcloudError("Not found", 404))

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch("app.api.files.folders.invalidate_folder_cache", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.invalidate_file_share_folder_cache",
                new_callable=AsyncMock,
            ),
            patch("app.api.files.folders.drop_folder_perms", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.drop_file_shares_under_prefix",
                new_callable=AsyncMock,
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/files/folders/{folder.id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_nc_503_drift_still_204(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)

        from app.services.nextcloud import NextcloudError

        nc_mock = MagicMock()
        nc_mock.delete = AsyncMock(side_effect=NextcloudError("Unavailable", 503))

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch("app.api.files.folders.invalidate_folder_cache", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.invalidate_file_share_folder_cache",
                new_callable=AsyncMock,
            ),
            patch("app.api.files.folders.drop_folder_perms", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.drop_file_shares_under_prefix",
                new_callable=AsyncMock,
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/files/folders/{folder.id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_folder_not_found_404(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/files/folders/{folder_id}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_revokes_file_shares_and_invalidates_cache(self):
        """F5: удаление папки отзывает шары поддерева и чистит кэш шар."""
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)

        nc_mock = MagicMock()
        nc_mock.delete = AsyncMock(return_value=None)

        with (
            patch("app.api.files.folders.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.folders.get_nc_service", return_value=nc_mock),
            patch("app.api.files.folders.invalidate_folder_cache", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.invalidate_file_share_folder_cache",
                new_callable=AsyncMock,
            ) as inval_shares,
            patch("app.api.files.folders.drop_folder_perms", new_callable=AsyncMock),
            patch(
                "app.api.files.folders.drop_file_shares_under_prefix",
                new_callable=AsyncMock,
            ) as drop_shares,
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/files/folders/{folder.id}")

        assert resp.status_code == 204
        executed = [str(c.args[0]) for c in db.execute.call_args_list if c.args]
        assert any("file_shares" in s and "revoked_at" in s for s in executed)
        inval_shares.assert_awaited_once()
        drop_shares.assert_awaited_once_with(folder.nc_path)
