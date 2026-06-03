"""Unit tests for app.api.kb.attachments endpoints."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_user(role: str = "editor", uid: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uid or uuid.uuid4(),
        role=role,
        email=f"{role}@test.local",
        full_name=f"{role} user",
        keycloak_id=None,
    )


def _make_article(*, id: uuid.UUID | None = None) -> MagicMock:
    a = MagicMock()
    a.id = id or uuid.uuid4()
    a.created_by = uuid.uuid4()
    a.deleted_at = None
    a.tags = []
    return a


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    r = AsyncMock()
    r.get.return_value = None
    return r


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis, require_admin
    from app.api.kb.attachments import router

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
    _app.dependency_overrides[require_admin] = _fake_user
    return _app


async def _request(app, method: str, url: str, *, files=None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.request(method, url, files=files)


def _make_file(article_id: uuid.UUID, *, mime: str = "image/png") -> MagicMock:
    f = MagicMock()
    f.id = uuid.uuid4()
    f.article_id = article_id
    f.filename = "abc_test.png"
    f.original_name = "test.png"
    f.size_bytes = 1234
    f.mime_type = mime
    f.created_at = datetime.now(UTC)
    f.uploaded_by = uuid.uuid4()
    return f


class TestListFiles:
    @pytest.mark.asyncio
    async def test_list_returns_items(self):
        user = _make_user()
        article = _make_article()
        db = _make_db()
        redis = _make_redis()

        files = [_make_file(article.id), _make_file(article.id, mime="text/plain")]
        files_res = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=files)))
        )
        db.execute.return_value = files_res

        app = _build_app(user, db, redis)
        with (
            patch("app.api.kb.attachments._get_article_or_404", AsyncMock(return_value=article)),
            patch("app.api.kb.attachments.require_article_permission", AsyncMock()),
        ):
            r = await _request(app, "GET", f"/kb/articles/{article.id}/files")

        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 2


class TestUploadFile:
    @pytest.mark.asyncio
    async def test_upload_safe_mime_success(self):
        user = _make_user()
        article = _make_article()
        db = _make_db()
        redis = _make_redis()

        async def _fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(UTC)

        db.refresh.side_effect = _fake_refresh

        app = _build_app(user, db, redis)
        with (
            patch("app.api.kb.attachments._get_article_or_404", AsyncMock(return_value=article)),
            patch("app.api.kb.attachments.require_article_permission", AsyncMock()),
            patch(
                "app.api.kb.attachments.stream_upload_to_path",
                AsyncMock(return_value=(123, "image/png")),
            ),
            patch(
                "app.api.kb.attachments.load_system_settings",
                return_value=MagicMock(kb_attachment_max_size_mb=10),
            ),
            patch("app.services.audit.push_audit_event", AsyncMock()),
        ):
            r = await _request(
                app,
                "POST",
                f"/kb/articles/{article.id}/files",
                files={"file": ("test.png", io.BytesIO(b"PNGDATA"), "image/png")},
            )

        assert r.status_code == 201
        data = r.json()
        assert data["mime_type"] == "image/png"
        assert data["original_name"] == "test.png"

    @pytest.mark.asyncio
    async def test_upload_forwards_safe_mime_whitelist(self):
        from app.api.kb.attachments import SAFE_MIME_TYPES

        user = _make_user()
        article = _make_article()
        db = _make_db()
        redis = _make_redis()

        async def _fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(UTC)

        db.refresh.side_effect = _fake_refresh

        stream_mock = AsyncMock(return_value=(100, "image/png"))
        app = _build_app(user, db, redis)
        with (
            patch("app.api.kb.attachments._get_article_or_404", AsyncMock(return_value=article)),
            patch("app.api.kb.attachments.require_article_permission", AsyncMock()),
            patch("app.api.kb.attachments.stream_upload_to_path", stream_mock),
            patch(
                "app.api.kb.attachments.load_system_settings",
                return_value=MagicMock(kb_attachment_max_size_mb=10),
            ),
            patch("app.services.audit.push_audit_event", AsyncMock()),
        ):
            r = await _request(
                app,
                "POST",
                f"/kb/articles/{article.id}/files",
                files={"file": ("test.png", io.BytesIO(b"PNGDATA"), "image/png")},
            )

        assert r.status_code == 201
        assert r.json()["mime_type"] == "image/png"
        assert stream_mock.await_args.kwargs["allowed_mimes"] is SAFE_MIME_TYPES


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_delete_404_when_missing(self):
        user = _make_user("editor")
        article = _make_article()
        db = _make_db()
        redis = _make_redis()

        # uploader lookup → None; access check passes via perm
        uploader_res = MagicMock(fetchone=MagicMock(return_value=None))
        file_res = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        db.execute.side_effect = [uploader_res, file_res]

        app = _build_app(user, db, redis)
        with (
            patch("app.api.kb.attachments._get_article_or_404", AsyncMock(return_value=article)),
            patch(
                "app.api.kb.attachments.resolve_article_permission",
                AsyncMock(return_value="editor"),
            ),
        ):
            r = await _request(
                app,
                "DELETE",
                f"/kb/articles/{article.id}/files/{uuid.uuid4()}",
            )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_403_when_not_owner_no_perm(self):
        user = _make_user("editor")
        article = _make_article()
        db = _make_db()
        redis = _make_redis()

        # uploader row exists but it's not this user
        uploader_row = MagicMock()
        uploader_row.__getitem__ = lambda self, idx: uuid.uuid4()  # different uuid
        uploader_res = MagicMock(fetchone=MagicMock(return_value=uploader_row))
        db.execute.side_effect = [uploader_res]

        app = _build_app(user, db, redis)
        with (
            patch("app.api.kb.attachments._get_article_or_404", AsyncMock(return_value=article)),
            patch(
                "app.api.kb.attachments.resolve_article_permission",
                AsyncMock(return_value="viewer"),
            ),
            patch("app.api.kb.attachments.perm_gte", MagicMock(return_value=False)),
        ):
            r = await _request(
                app,
                "DELETE",
                f"/kb/articles/{article.id}/files/{uuid.uuid4()}",
            )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_success_when_owner(self):
        uid = uuid.uuid4()
        user = _make_user("editor", uid=uid)
        article = _make_article()
        db = _make_db()
        redis = _make_redis()

        kb_file = _make_file(article.id)
        kb_file.uploaded_by = uid

        uploader_row = MagicMock()
        uploader_row.__getitem__ = lambda self, idx: uid
        uploader_res = MagicMock(fetchone=MagicMock(return_value=uploader_row))
        file_res = MagicMock(scalar_one_or_none=MagicMock(return_value=kb_file))
        db.execute.side_effect = [uploader_res, file_res]
        db.delete = AsyncMock()

        app = _build_app(user, db, redis)
        with (
            patch("app.api.kb.attachments._get_article_or_404", AsyncMock(return_value=article)),
            patch(
                "app.api.kb.attachments.resolve_article_permission",
                AsyncMock(return_value="viewer"),
            ),
            patch("app.api.kb.attachments.perm_gte", MagicMock(return_value=False)),
            patch("app.api.kb.attachments.try_remove_empty_article_dir", AsyncMock()),
            patch("pathlib.Path.unlink"),
        ):
            r = await _request(
                app,
                "DELETE",
                f"/kb/articles/{article.id}/files/{kb_file.id}",
            )
        assert r.status_code == 204
