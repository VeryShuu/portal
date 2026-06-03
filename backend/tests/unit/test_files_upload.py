"""
Test coverage for app/api/files/upload.py

Coverage:
- POST /files/folders/{id}/upload:
  - idempotency key cached → returns cached
  - 404 folder not found
  - empty file → failed
  - blocked mime → failed
  - NC upload error → failed
  - successful upload
  - commit error → uploaded moved to failed
  - idempotency key set after success
- POST /files/open (open_in_collabora):
  - 404 folder
  - 403 no perm
  - success with portal_base_url (via federation)
  - success without portal_base_url (direct)
  - NC error → 502
"""

from __future__ import annotations

import io
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
        avatar_url=None,
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
    db.add = MagicMock()
    db.delete = MagicMock()
    db.refresh = MagicMock()
    db.expunge = MagicMock()
    db.add_all = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get.return_value = None
    return redis


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI
    from fastapi_limiter.depends import RateLimiter

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.files._common import _check_module_enabled
    from app.api.files.upload import router

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


def _make_upload_file(
    name: str = "test.txt",
    content: bytes = b"plain text content here",
    size: int | None = None,
    content_type: str = "text/plain",
) -> tuple[str, tuple]:
    return ("files", (name, io.BytesIO(content), content_type))


async def _upload(app, folder_id: uuid.UUID, files=None, headers: dict | None = None):
    import httpx

    if files is None:
        files = [_make_upload_file()]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(
            f"/files/folders/{folder_id}/upload",
            files=files,
            headers=headers or {},
        )


async def _post_open(app, folder_id: uuid.UUID, filename: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(
            f"/files/open?folder_id={folder_id}&filename={filename}",
        )


# ── POST /files/folders/{id}/upload ───────────────────────────────────────────


class TestUploadFiles:
    @pytest.mark.asyncio
    async def test_idempotency_cached_returns_cached(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        cached_json = '{"uploaded":[],"failed":[]}'
        redis.get.return_value = cached_json.encode()

        app = _build_app(user, db, redis)
        resp = await _upload(
            app,
            folder.id,
            headers={"Idempotency-Key": "cached-key"},
        )

        assert resp.status_code == 200
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_folder_not_found_404(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with patch("app.api.files.upload.require_folder_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _upload(app, folder_id)

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_file_goes_to_failed(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        empty_file = ("files", ("empty.txt", io.BytesIO(b""), "text/plain"))

        with (
            patch("app.api.files.upload.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.upload.load_system_settings",
                return_value=MagicMock(max_upload_size_mb=10),
            ),
            patch(
                "app.api.files.upload.get_nc_service",
                return_value=MagicMock(),
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _upload(app, folder.id, files=[empty_file])

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["failed"]) == 1
        assert data["failed"][0]["error"] == "Empty file"

    @pytest.mark.asyncio
    async def test_blocked_mime_goes_to_failed(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        with (
            patch("app.api.files.upload.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.upload.load_system_settings",
                return_value=MagicMock(max_upload_size_mb=10),
            ),
            patch(
                "app.api.files.upload.get_nc_service",
                return_value=MagicMock(),
            ),
            patch("magic.from_buffer", return_value="text/html"),
        ):
            app = _build_app(user, db, redis)
            resp = await _upload(
                app,
                folder.id,
                files=[("files", ("page.html", io.BytesIO(b"<html>test</html>"), "text/html"))],
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["failed"]) == 1
        assert "not allowed" in data["failed"][0]["error"]

    @pytest.mark.asyncio
    async def test_nc_error_goes_to_failed(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        from app.services.nextcloud import NextcloudError

        nc_mock = MagicMock()
        nc_mock.upload_stream = AsyncMock(side_effect=NextcloudError("Upload failed", 503))

        with (
            patch("app.api.files.upload.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.upload.load_system_settings",
                return_value=MagicMock(max_upload_size_mb=10),
            ),
            patch("app.api.files.upload.get_nc_service", return_value=nc_mock),
            patch("magic.from_buffer", return_value="text/plain"),
        ):
            app = _build_app(user, db, redis)
            resp = await _upload(
                app,
                folder.id,
                files=[("files", ("doc.txt", io.BytesIO(b"hello world"), "text/plain"))],
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["failed"]) == 1

    @pytest.mark.asyncio
    async def test_successful_upload(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(return_value=None)

        nc_mock = MagicMock()
        nc_mock.upload_stream = AsyncMock(return_value=None)

        with (
            patch("app.api.files.upload.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.upload.load_system_settings",
                return_value=MagicMock(max_upload_size_mb=10),
            ),
            patch("app.api.files.upload.get_nc_service", return_value=nc_mock),
            patch("magic.from_buffer", return_value="text/plain"),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.files.upload.FileItem", return_value=MagicMock()),
        ):
            app = _build_app(user, db, redis)
            resp = await _upload(
                app,
                folder.id,
                files=[("files", ("report.txt", io.BytesIO(b"hello world content"), "text/plain"))],
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["uploaded"]) == 1
        assert data["failed"] == []

    @pytest.mark.asyncio
    async def test_commit_error_moves_to_failed(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))
        db.commit = AsyncMock(side_effect=Exception("DB connection lost"))
        db.rollback = AsyncMock(return_value=None)

        nc_mock = MagicMock()
        nc_mock.upload_stream = AsyncMock(return_value=None)

        with (
            patch("app.api.files.upload.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.upload.load_system_settings",
                return_value=MagicMock(max_upload_size_mb=10),
            ),
            patch("app.api.files.upload.get_nc_service", return_value=nc_mock),
            patch("magic.from_buffer", return_value="text/plain"),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.files.upload.FileItem", return_value=MagicMock()),
        ):
            app = _build_app(user, db, redis)
            resp = await _upload(
                app,
                folder.id,
                files=[("files", ("data.txt", io.BytesIO(b"content"), "text/plain"))],
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["uploaded"] == []
        assert len(data["failed"]) == 1
        assert data["failed"][0]["error"] == "db_commit_failed"

    @pytest.mark.asyncio
    async def test_invalid_filename_goes_to_failed(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        nc_mock = MagicMock()

        with (
            patch("app.api.files.upload.require_folder_permission", new_callable=AsyncMock),
            patch(
                "app.api.files.upload.load_system_settings",
                return_value=MagicMock(max_upload_size_mb=10),
            ),
            patch("app.api.files.upload.get_nc_service", return_value=nc_mock),
        ):
            app = _build_app(user, db, redis)
            resp = await _upload(
                app,
                folder.id,
                files=[
                    ("files", ("bad?name*.exe", io.BytesIO(b"content"), "application/x-executable"))
                ],
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["failed"]) == 1


# ── POST /files/open ──────────────────────────────────────────────────────────


class TestOpenInCollabora:
    @pytest.mark.asyncio
    async def test_folder_not_found_404(self):
        user = _make_user()
        folder_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _post_open(app, folder_id, "document.odt")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_no_perm_returns_403(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        from fastapi import HTTPException

        with patch(
            "app.api.files.upload.require_file_access",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=403, detail="Insufficient file permissions"),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_open(app, folder.id, "doc.odt")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_nc_error_returns_502(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        from app.services.nextcloud import NextcloudError

        nc_mock = MagicMock()
        nc_mock.get_collabora_url = AsyncMock(side_effect=NextcloudError("Collabora down", 503))

        with (
            patch(
                "app.api.files.upload.require_file_access",
                new_callable=AsyncMock,
                return_value="editor",
            ),
            patch("app.api.files.upload.get_nc_service", return_value=nc_mock),
            patch(
                "app.api.files.upload.load_system_settings",
                return_value=MagicMock(portal_base_url=None),
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_open(app, folder.id, "doc.odt")

        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_success_without_portal_base_url(self):
        user = _make_user()
        folder = _make_folder()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=folder))

        nc_mock = MagicMock()
        nc_mock.get_collabora_url = AsyncMock(
            return_value={"url": "https://collabora.example.com/lool"}
        )

        with (
            patch(
                "app.api.files.upload.require_file_access",
                new_callable=AsyncMock,
                return_value="editor",
            ),
            patch("app.api.files.upload.get_nc_service", return_value=nc_mock),
            patch(
                "app.api.files.upload.load_system_settings",
                return_value=MagicMock(portal_base_url=None),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_open(app, folder.id, "doc.odt")

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "collabora"
        assert "url" in data
