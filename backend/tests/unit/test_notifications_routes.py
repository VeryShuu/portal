"""Unit tests for app/api/notifications.py — CRUD routes and SSE stream."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("httpx", reason="httpx not installed")


def _make_user(**kw) -> SimpleNamespace:
    return SimpleNamespace(
        id=kw.get("id", uuid.uuid4()),
        role=kw.get("role", "reader"),
        email=kw.get("email", "u@test.local"),
    )


def _make_notif(**kw):
    n = MagicMock()
    n.id = kw.get("id", uuid.uuid4())
    n.user_id = kw.get("user_id", uuid.uuid4())
    n.type = kw.get("type", "news_published")
    n.title = kw.get("title", "Hello")
    n.body = kw.get("body", None)
    n.link = kw.get("link", "/news/1")
    n.is_read = kw.get("is_read", False)
    n.read_at = kw.get("read_at", None)
    n.created_at = kw.get("created_at", datetime.now(UTC))
    n.updated_at = kw.get("updated_at", datetime.now(UTC))
    return n


def _build_app(user, db, redis=None):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.notifications import router

    app = FastAPI()
    app.include_router(router)

    if redis is None:
        redis = AsyncMock()

    async def _user():
        return user

    async def _db():
        return db

    async def _redis():
        return redis

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    return app


async def _get(app, url, **kw):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url, **kw)


async def _post(app, url, **kw):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, **kw)


async def _delete(app, url, **kw):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.delete(url, **kw)


def _make_db_with_notifications(notifications, total_all=None, unread_count=0):
    db = AsyncMock()

    stats_row = MagicMock()
    stats_row.total_all = total_all if total_all is not None else len(notifications)
    stats_row.unread_count = unread_count

    stats_result = MagicMock()
    stats_result.one.return_value = stats_row

    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = notifications

    db.execute.side_effect = [stats_result, items_result]
    return db


class TestListNotifications:
    @pytest.mark.asyncio
    async def test_list_all_empty(self):
        user = _make_user()
        db = _make_db_with_notifications([], total_all=0, unread_count=0)
        app = _build_app(user, db)

        r = await _get(app, "/notifications")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_all_returns_items(self):
        user = _make_user()
        db = _make_db_with_notifications([], total_all=1, unread_count=1)
        app = _build_app(user, db)

        r = await _get(app, "/notifications")

        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_list_unread_only(self):
        user = _make_user()
        db = _make_db_with_notifications([], total_all=5, unread_count=0)
        app = _build_app(user, db)

        r = await _get(app, "/notifications?unread_only=true")

        assert r.status_code == 200


class TestUnreadCount:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        user = _make_user()
        db = AsyncMock()
        app = _build_app(user, db)

        with patch("app.api.notifications.get_unread_count", AsyncMock(return_value=7)):
            r = await _get(app, "/notifications/unread-count")

        assert r.status_code == 200
        assert r.json()["unread_count"] == 7


class TestMarkRead:
    @pytest.mark.asyncio
    async def test_marks_unread_notification(self):
        user = _make_user()
        notif = _make_notif(user_id=user.id, is_read=False)

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = notif
        db.execute.return_value = result

        app = _build_app(user, db)
        r = await _post(app, f"/notifications/{notif.id}/read")

        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert notif.is_read is True
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_read_no_extra_commit(self):
        user = _make_user()
        notif = _make_notif(user_id=user.id, is_read=True)

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = notif
        db.execute.return_value = result

        app = _build_app(user, db)
        r = await _post(app, f"/notifications/{notif.id}/read")

        assert r.status_code == 200
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self):
        user = _make_user()
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        app = _build_app(user, db)
        r = await _post(app, f"/notifications/{uuid.uuid4()}/read")

        assert r.status_code == 404


class TestMarkAllRead:
    @pytest.mark.asyncio
    async def test_marks_all_read(self):
        user = _make_user()
        db = AsyncMock()
        app = _build_app(user, db)

        r = await _post(app, "/notifications/read-all")

        assert r.status_code == 200
        assert r.json() == {"ok": True}
        db.execute.assert_called_once()
        db.commit.assert_called_once()


class TestDeleteNotification:
    @pytest.mark.asyncio
    async def test_delete_success(self):
        user = _make_user()
        notif = _make_notif(user_id=user.id)

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = notif
        db.execute.return_value = result

        app = _build_app(user, db)
        r = await _delete(app, f"/notifications/{notif.id}")

        assert r.status_code == 204
        db.delete.assert_called_once_with(notif)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        user = _make_user()
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        app = _build_app(user, db)
        r = await _delete(app, f"/notifications/{uuid.uuid4()}")

        assert r.status_code == 404


class TestSSEStream:
    @pytest.mark.asyncio
    async def test_stream_per_user_limit_429(self):
        import httpx

        user = _make_user()
        redis = AsyncMock()

        sys_cfg = MagicMock()
        sys_cfg.sse_max_connections_per_user = 2
        sys_cfg.sse_max_connections_global = 100

        redis.eval = AsyncMock(return_value=-1)

        db = AsyncMock()
        app = _build_app(user, db, redis)

        async def _fake_sys_cfg(r):
            return sys_cfg

        with patch("app.api.notifications.load_system_settings_shared", _fake_sys_cfg):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get("/notifications/stream")

        assert r.status_code == 429

    @pytest.mark.asyncio
    async def test_stream_global_limit_429(self):
        import httpx

        user = _make_user()
        redis = AsyncMock()

        sys_cfg = MagicMock()
        sys_cfg.sse_max_connections_per_user = 5
        sys_cfg.sse_max_connections_global = 10

        redis.eval = AsyncMock(return_value=-2)

        db = AsyncMock()
        app = _build_app(user, db, redis)

        async def _fake_sys_cfg(r):
            return sys_cfg

        with patch("app.api.notifications.load_system_settings_shared", _fake_sys_cfg):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get("/notifications/stream")

        assert r.status_code == 429

    @pytest.mark.asyncio
    async def test_stream_redis_error_503(self):
        import httpx

        from redis.exceptions import RedisError

        user = _make_user()
        redis = AsyncMock()

        sys_cfg = MagicMock()
        sys_cfg.sse_max_connections_per_user = 5
        sys_cfg.sse_max_connections_global = 100

        redis.eval = AsyncMock(side_effect=RedisError("connection refused"))

        db = AsyncMock()
        app = _build_app(user, db, redis)

        async def _fake_sys_cfg(r):
            return sys_cfg

        with patch("app.api.notifications.load_system_settings_shared", _fake_sys_cfg):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get("/notifications/stream")

        assert r.status_code == 503
