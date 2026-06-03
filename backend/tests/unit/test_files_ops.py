"""Unit-тесты для app/api/files/files_ops.py.

Покрытие:
- _bulk_inflight_key: формат ключа
- _try_set_inflight: lock acquired / already busy
- _clear_inflight: вызывает redis.delete, проглатывает ошибку
- _validate_bulk_names: пустой / дубликаты / невалидное имя / happy-path
- DELETE /files/file: success / nextcloud 404 ignored / nextcloud error / 404 folder / 403 no perm
- POST /files/folders/{id}/bulk-delete: 409 inflight / valid names / nc error / empty names
- POST /files/folders/{src}/bulk-move: same-folder 422 / 409 inflight / nc 412 conflict / success
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
    nc_path: str = "PortalFiles/folder1",
) -> MagicMock:
    f = MagicMock()
    f.id = id or uuid.uuid4()
    f.nc_path = nc_path
    f.name = "folder1"
    f.created_at = datetime.now(UTC)
    return f


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    return AsyncMock()


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI
    from fastapi_limiter.depends import RateLimiter

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.files._common import _check_module_enabled
    from app.api.files.files_ops import router

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
    _app.dependency_overrides[RateLimiter] = lambda: None
    return _app


async def _delete(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.delete(url)


async def _post(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, json=json)


# ── Unit tests for helpers ────────────────────────────────────────────────────


class TestBulkInflightKey:
    def test_key_contains_user_id(self):
        from app.api.files.files_ops import _bulk_inflight_key

        uid = uuid.uuid4()
        key = _bulk_inflight_key(uid)
        assert str(uid) in key
        assert key.startswith("bulk:inflight:")

    def test_key_is_deterministic(self):
        from app.api.files.files_ops import _bulk_inflight_key

        uid = uuid.uuid4()
        assert _bulk_inflight_key(uid) == _bulk_inflight_key(uid)


class TestTrySetInflight:
    @pytest.mark.asyncio
    async def test_returns_true_when_lock_acquired(self):
        from app.api.files.files_ops import _try_set_inflight

        redis = AsyncMock()
        redis.set.return_value = True

        result = await _try_set_inflight(redis, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_already_busy(self):
        from app.api.files.files_ops import _try_set_inflight

        redis = AsyncMock()
        redis.set.return_value = None

        result = await _try_set_inflight(redis, uuid.uuid4())
        assert result is False


class TestClearInflight:
    @pytest.mark.asyncio
    async def test_calls_redis_delete(self):
        from app.api.files.files_ops import _clear_inflight

        redis = AsyncMock()
        uid = uuid.uuid4()
        await _clear_inflight(redis, uid)
        redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_swallows_redis_error(self):
        from app.api.files.files_ops import _clear_inflight

        redis = AsyncMock()
        redis.delete.side_effect = Exception("redis down")

        await _clear_inflight(redis, uuid.uuid4())


class TestValidateBulkNames:
    def test_empty_list_returns_empty(self):
        from app.api.files.files_ops import _validate_bulk_names

        valid, invalid = _validate_bulk_names([])
        assert valid == []
        assert invalid == []

    def test_deduplicates_names(self):
        from app.api.files.files_ops import _validate_bulk_names

        valid, invalid = _validate_bulk_names(["file.txt", "file.txt", "other.txt"])
        assert len(valid) == 2
        assert "file.txt" in valid
        assert "other.txt" in valid

    def test_invalid_name_goes_to_invalid(self):
        from app.api.files.files_ops import _validate_bulk_names

        valid, invalid = _validate_bulk_names(["bad?name.txt", "ok.txt"])
        assert "ok.txt" in valid
        assert any(i.name == "bad?name.txt" for i in invalid)

    def test_valid_names_returned(self):
        from app.api.files.files_ops import _validate_bulk_names

        valid, invalid = _validate_bulk_names(["doc.pdf", "photo.jpg"])
        assert len(valid) == 2
        assert invalid == []

    def test_strips_path_components(self):
        from app.api.files.files_ops import _validate_bulk_names

        valid, invalid = _validate_bulk_names(["folder/file.txt"])
        assert "file.txt" in valid


# ── DELETE /files/file ────────────────────────────────────────────────────────


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_deletes_file_successfully(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        folder = _make_folder(id=folder_id)
        db = _make_db()
        redis = _make_redis()

        fi = MagicMock()
        fi.deleted_at = None
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=folder)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=fi)),
        ]

        nc = AsyncMock()
        nc.delete = AsyncMock()

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.files_ops.get_nc_service", return_value=nc),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.files.files_ops.revoke_file_shares", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/files/file?folder_id={folder_id}&filename=test.txt")

        assert resp.status_code == 204
        nc.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_nextcloud_404_is_ignored(self):
        """NC 404 on delete is OK — file already gone."""
        from app.services.nextcloud import NextcloudError

        user = _make_user()
        folder_id = uuid.uuid4()
        folder = _make_folder(id=folder_id)
        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=folder)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        nc = AsyncMock()
        nc.delete = AsyncMock(side_effect=NextcloudError(404, "not found"))

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.files_ops.get_nc_service", return_value=nc),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.files.files_ops.revoke_file_shares", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/files/file?folder_id={folder_id}&filename=test.txt")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_nextcloud_error_returns_502(self):
        from app.services.nextcloud import NextcloudError

        user = _make_user()
        folder_id = uuid.uuid4()
        folder = _make_folder(id=folder_id)
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        nc = AsyncMock()
        nc.delete = AsyncMock(side_effect=NextcloudError(503, "unavailable"))

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.files_ops.get_nc_service", return_value=nc),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/files/file?folder_id={folder_id}&filename=test.txt")

        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_folder_not_found_returns_404(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/files/file?folder_id={folder_id}&filename=test.txt")

        assert resp.status_code == 404


# ── POST /files/folders/{id}/bulk-delete ─────────────────────────────────────


class TestBulkDeleteFiles:
    @pytest.mark.asyncio
    async def test_returns_409_when_inflight_busy(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        folder = _make_folder(id=folder_id)
        db = _make_db()
        redis = _make_redis()
        redis.set.return_value = None

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.files_ops.get_nc_service"),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                f"/files/folders/{folder_id}/bulk-delete",
                json={"filenames": ["file.txt"]},
            )

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_bulk_delete_success(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        folder = _make_folder(id=folder_id)
        db = _make_db()
        redis = _make_redis()
        redis.set.return_value = True

        fi = MagicMock()
        fi.deleted_at = None

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=folder)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[fi])))),
        ]

        nc = AsyncMock()
        nc.delete = AsyncMock()

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.files_ops.get_nc_service", return_value=nc),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.files.files_ops.invalidate_folder_cache", new_callable=AsyncMock),
            patch("app.api.files.files_ops.revoke_file_shares", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                f"/files/folders/{folder_id}/bulk-delete",
                json={"filenames": ["file.txt"]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["deleted"]) == 1
        assert data["deleted"][0]["name"] == "file.txt"
        assert data["deleted"][0]["success"] is True

    @pytest.mark.asyncio
    async def test_bulk_delete_nc_error_marks_failed(self):
        from app.services.nextcloud import NextcloudError

        user = _make_user()
        folder_id = uuid.uuid4()
        folder = _make_folder(id=folder_id)
        db = _make_db()
        redis = _make_redis()
        redis.set.return_value = True

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        nc = AsyncMock()
        nc.delete = AsyncMock(side_effect=NextcloudError(500, "server error"))

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.files_ops.get_nc_service", return_value=nc),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.files.files_ops.invalidate_folder_cache", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                f"/files/folders/{folder_id}/bulk-delete",
                json={"filenames": ["file.txt"]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["failed"]) == 1
        assert data["failed"][0]["success"] is False

    @pytest.mark.asyncio
    async def test_bulk_delete_nc_404_treated_as_success(self):
        """NC 404 during bulk delete is treated as already deleted → success."""
        from app.services.nextcloud import NextcloudError

        user = _make_user()
        folder_id = uuid.uuid4()
        folder = _make_folder(id=folder_id)
        db = _make_db()
        redis = _make_redis()
        redis.set.return_value = True

        fi = MagicMock()
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=folder)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[fi])))),
        ]

        nc = AsyncMock()
        nc.delete = AsyncMock(side_effect=NextcloudError(404, "not found"))

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.files_ops.get_nc_service", return_value=nc),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.files.files_ops.invalidate_folder_cache", new_callable=AsyncMock),
            patch("app.api.files.files_ops.revoke_file_shares", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                f"/files/folders/{folder_id}/bulk-delete",
                json={"filenames": ["missing.txt"]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"][0]["success"] is True


# ── POST /files/folders/{src}/bulk-move ──────────────────────────────────────


class TestBulkMoveFiles:
    @pytest.mark.asyncio
    async def test_returns_422_when_same_folder(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        resp = await _post(
            app,
            f"/files/folders/{folder_id}/bulk-move",
            json={"filenames": ["file.txt"], "target_folder_id": str(folder_id)},
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_409_when_inflight_busy(self):
        user = _make_user()
        src_id = uuid.uuid4()
        dst_id = uuid.uuid4()
        src_folder = _make_folder(id=src_id, nc_path="PortalFiles/src")
        dst_folder = _make_folder(id=dst_id, nc_path="PortalFiles/dst")

        db = _make_db()
        redis = _make_redis()
        redis.set.return_value = None

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=src_folder)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=dst_folder)),
        ]

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.files_ops.get_settings",
                return_value=MagicMock(nc_files_root="PortalFiles"),
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                f"/files/folders/{src_id}/bulk-move",
                json={"filenames": ["file.txt"], "target_folder_id": str(dst_id)},
            )

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_nc_412_conflict_marks_failed(self):
        from app.services.nextcloud import NextcloudError

        user = _make_user()
        src_id = uuid.uuid4()
        dst_id = uuid.uuid4()
        src_folder = _make_folder(id=src_id, nc_path="PortalFiles/src")
        dst_folder = _make_folder(id=dst_id, nc_path="PortalFiles/dst")

        db = _make_db()
        redis = _make_redis()
        redis.set.return_value = True

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=src_folder)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=dst_folder)),
        ]

        nc = AsyncMock()
        nc.move = AsyncMock(side_effect=NextcloudError(412, "conflict"))

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.files_ops.get_nc_service", return_value=nc),
            patch(
                "app.api.files.files_ops.get_settings",
                return_value=MagicMock(nc_files_root="PortalFiles"),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.files.files_ops.invalidate_folder_cache", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                f"/files/folders/{src_id}/bulk-move",
                json={"filenames": ["file.txt"], "target_folder_id": str(dst_id)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"][0]["error"] == "name_conflict"

    @pytest.mark.asyncio
    async def test_bulk_move_success(self):
        user = _make_user()
        src_id = uuid.uuid4()
        dst_id = uuid.uuid4()
        src_folder = _make_folder(id=src_id, nc_path="PortalFiles/src")
        dst_folder = _make_folder(id=dst_id, nc_path="PortalFiles/dst")

        db = _make_db()
        redis = _make_redis()
        redis.set.return_value = True

        fi = MagicMock()
        fi.folder_id = src_id
        fi.nc_path = "PortalFiles/src/file.txt"

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=src_folder)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=dst_folder)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=fi)),
        ]

        nc = AsyncMock()
        nc.move = AsyncMock()

        with (
            patch("app.api.files.files_ops.require_folder_permission", new_callable=AsyncMock),
            patch("app.api.files.files_ops.get_nc_service", return_value=nc),
            patch(
                "app.api.files.files_ops.get_settings",
                return_value=MagicMock(nc_files_root="PortalFiles"),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.files.files_ops.invalidate_folder_cache", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                f"/files/folders/{src_id}/bulk-move",
                json={"filenames": ["file.txt"], "target_folder_id": str(dst_id)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["moved"][0]["success"] is True
        nc.move.assert_called_once()
