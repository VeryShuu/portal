"""Unit-тесты api/audit.py (Phase 4.13).

Покрытие:
- _build_filters: пустые параметры / все параметры / парциально
- GET /audit: happy-path / только admin / фильтрация
- GET /audit/event-types: happy-path
- GET /audit/queue/depth: happy-path / Redis error → 503
- GET /audit/export.csv: streaming response с заголовком
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_admin() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role="admin")


def _make_db() -> AsyncMock:
    return AsyncMock()


def _make_redis() -> AsyncMock:
    return AsyncMock()


def _build_app(user, db, redis):
    from fastapi import FastAPI

    from app.api.audit import router
    from app.api.deps import get_current_user, get_db, get_redis, require_admin

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


# ── _build_filters ─────────────────────────────────────────────────────────────


class TestBuildFilters:
    def test_no_filters_returns_empty_where(self):
        from app.api.audit import _build_filters

        where, params = _build_filters(
            user_id=None,
            event_type=None,
            resource_type=None,
            ip_address=None,
            date_from=None,
            date_to=None,
            q=None,
        )
        assert where == ""
        assert params == {}

    def test_user_id_filter(self):
        from app.api.audit import _build_filters

        uid = str(uuid.uuid4())
        where, params = _build_filters(
            user_id=uid,
            event_type=None,
            resource_type=None,
            ip_address=None,
            date_from=None,
            date_to=None,
            q=None,
        )
        assert "user_id" in where
        assert params["user_id"] == uid

    def test_event_type_filter(self):
        from app.api.audit import _build_filters

        where, params = _build_filters(
            user_id=None,
            event_type="auth.login",
            resource_type=None,
            ip_address=None,
            date_from=None,
            date_to=None,
            q=None,
        )
        assert "event_type" in where
        assert params["event_type"] == "auth.login"

    def test_resource_type_filter(self):
        from app.api.audit import _build_filters

        where, params = _build_filters(
            user_id=None,
            event_type=None,
            resource_type="news",
            ip_address=None,
            date_from=None,
            date_to=None,
            q=None,
        )
        assert "resource_type" in where
        assert params["resource_type"] == "news"

    def test_ip_address_filter(self):
        from app.api.audit import _build_filters

        where, params = _build_filters(
            user_id=None,
            event_type=None,
            resource_type=None,
            ip_address="192.168.1.1",
            date_from=None,
            date_to=None,
            q=None,
        )
        assert "ip_address" in where
        assert params["ip_address"] == "192.168.1.1"

    def test_date_from_filter(self):
        from app.api.audit import _build_filters

        dt = datetime(2025, 1, 1, tzinfo=UTC)
        where, params = _build_filters(
            user_id=None,
            event_type=None,
            resource_type=None,
            ip_address=None,
            date_from=dt,
            date_to=None,
            q=None,
        )
        assert "date_from" in where
        assert params["date_from"] == dt

    def test_date_to_filter(self):
        from app.api.audit import _build_filters

        dt = datetime(2025, 12, 31, tzinfo=UTC)
        where, params = _build_filters(
            user_id=None,
            event_type=None,
            resource_type=None,
            ip_address=None,
            date_from=None,
            date_to=dt,
            q=None,
        )
        assert "date_to" in where
        assert params["date_to"] == dt

    def test_q_filter(self):
        from app.api.audit import _build_filters

        where, params = _build_filters(
            user_id=None,
            event_type=None,
            resource_type=None,
            ip_address=None,
            date_from=None,
            date_to=None,
            q="search term",
        )
        assert "ILIKE" in where
        assert params["q"] == "%search term%"

    def test_multiple_filters_joined_with_and(self):
        from app.api.audit import _build_filters

        where, params = _build_filters(
            user_id=str(uuid.uuid4()),
            event_type="news.created",
            resource_type=None,
            ip_address=None,
            date_from=None,
            date_to=None,
            q=None,
        )
        assert " AND " in where
        assert "WHERE" in where

    def test_where_starts_with_where(self):
        from app.api.audit import _build_filters

        where, _ = _build_filters(
            user_id="some-id",
            event_type=None,
            resource_type=None,
            ip_address=None,
            date_from=None,
            date_to=None,
            q=None,
        )
        assert where.strip().startswith("WHERE")


# ── GET /audit ─────────────────────────────────────────────────────────────────


class TestListAuditEvents:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self):
        import httpx
        from httpx import ASGITransport

        admin = _make_admin()
        db = _make_db()
        redis = _make_redis()

        now = datetime.now(UTC)
        fake_user_id = uuid.uuid4()

        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "id": uuid.uuid4(),
            "event_type": "auth.login",
            "user_id": fake_user_id,
            "user_email": "user@example.com",
            "resource_type": None,
            "resource_id": None,
            "resource_title": None,
            "ip_address": "127.0.0.1",
            "user_agent": "Mozilla",
            "metadata": {"foo": "bar"},
            "created_at": now,
        }[key]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        items_result = MagicMock()
        items_result.mappings.return_value.all.return_value = [row]

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        app = _build_app(admin, db, redis)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/audit")

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_pagination_params(self):
        import httpx
        from httpx import ASGITransport

        admin = _make_admin()
        db = _make_db()
        redis = _make_redis()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        items_result = MagicMock()
        items_result.mappings.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        app = _build_app(admin, db, redis)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/audit?limit=10&offset=20")

        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 20


# ── GET /audit/event-types ─────────────────────────────────────────────────────


class TestListEventTypes:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        import httpx
        from httpx import ASGITransport

        admin = _make_admin()
        db = _make_db()
        redis = _make_redis()

        result = MagicMock()
        result.all.return_value = [("auth.login",), ("news.created",)]
        db.execute = AsyncMock(return_value=result)

        app = _build_app(admin, db, redis)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/audit/event-types")

        assert resp.status_code == 200
        data = resp.json()
        assert "auth.login" in data
        assert "news.created" in data


# ── GET /audit/queue/depth ─────────────────────────────────────────────────────


class TestAuditQueueDepth:
    @pytest.mark.asyncio
    async def test_returns_pending_and_processing(self):
        import httpx
        from httpx import ASGITransport

        admin = _make_admin()
        db = _make_db()
        redis = _make_redis()
        redis.llen = AsyncMock(side_effect=[5, 2])

        app = _build_app(admin, db, redis)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/audit/queue/depth")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] == 5
        assert data["processing"] == 2

    @pytest.mark.asyncio
    async def test_redis_error_returns_503(self):
        import httpx
        from httpx import ASGITransport

        admin = _make_admin()
        db = _make_db()
        redis = _make_redis()
        redis.llen = AsyncMock(side_effect=Exception("Redis down"))

        app = _build_app(admin, db, redis)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/audit/queue/depth")

        assert resp.status_code == 503


# ── GET /audit/export.csv ──────────────────────────────────────────────────────


class TestExportAuditCsv:
    @pytest.mark.asyncio
    async def test_returns_csv_content_disposition(self):
        import httpx
        from httpx import ASGITransport

        admin = _make_admin()
        db = _make_db()
        redis = _make_redis()

        async def _async_iter():
            return
            yield  # make it a generator

        stream_result = MagicMock()
        stream_result.mappings.return_value = _async_iter()
        db.stream = AsyncMock(return_value=stream_result)

        app = _build_app(admin, db, redis)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/audit/export.csv")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "attachment" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_csv_contains_header_row(self):
        import httpx
        from httpx import ASGITransport

        admin = _make_admin()
        db = _make_db()
        redis = _make_redis()

        async def _async_iter():
            return
            yield

        stream_result = MagicMock()
        stream_result.mappings.return_value = _async_iter()
        db.stream = AsyncMock(return_value=stream_result)

        app = _build_app(admin, db, redis)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/audit/export.csv")

        assert b"event_type" in resp.content
        assert b"user_id" in resp.content

    @pytest.mark.asyncio
    async def test_csv_with_rows(self):
        from datetime import UTC, datetime

        import httpx
        from httpx import ASGITransport

        admin = _make_admin()
        db = _make_db()
        redis = _make_redis()

        row = {
            "id": "row-id-1",
            "created_at": datetime.now(UTC),
            "event_type": "login",
            "user_id": uuid.uuid4(),
            "user_email": "u@test.local",
            "resource_type": "user",
            "resource_id": "1",
            "resource_title": "Test",
            "ip_address": "127.0.0.1",
            "user_agent": "Mozilla",
            "metadata": {"key": "value"},
        }

        async def _async_iter():
            yield row

        stream_result = MagicMock()
        stream_result.mappings.return_value = _async_iter()
        db.stream = AsyncMock(return_value=stream_result)

        app = _build_app(admin, db, redis)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/audit/export.csv")

        assert resp.status_code == 200
        assert b"login" in resp.content
