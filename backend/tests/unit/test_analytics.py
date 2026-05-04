from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

_ALLOWED_EVENTS = {
    "files.file_downloaded",
    "photos.photo_downloaded",
    "kb.article_exported_pdf",
    "kb.article_exported_docx",
    "news.exported",
}


def _make_scalar_row(value: int = 0):
    row = MagicMock()
    row.total_users = value
    row.active_users_30d = value
    row.new_users_30d = value
    row.published_news_30d = value
    row.published_articles_30d = value
    row.audit_24h = value
    row.logins_24h = value
    row.active_users_1h = value
    return row


def _make_db_session(scalar_value: int = 0, mappings_rows: list | None = None):
    session = MagicMock()
    scalar_row = _make_scalar_row(scalar_value)
    result = MagicMock()
    result.scalar_one = MagicMock(return_value=scalar_value)
    result.one = MagicMock(return_value=scalar_row)
    result.all = MagicMock(return_value=[])
    mapping_result = MagicMock()
    mapping_result.all = MagicMock(return_value=mappings_rows or [])
    result.mappings = MagicMock(return_value=mapping_result)
    session.execute = AsyncMock(return_value=result)
    return session


def _authed_admin_app(app, user_factory):
    from app.api.deps import get_current_user, get_db

    user = user_factory(role="admin")

    async def _fake_user():
        return user

    async def _fake_db():
        yield _make_db_session()

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db
    return app


async def test_dashboard_returns_200(app, user_factory):
    _authed_admin_app(app, user_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/dashboard")
    assert r.status_code == 200


async def test_dashboard_response_has_required_top_level_keys(app, user_factory):
    _authed_admin_app(app, user_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/dashboard")
    body = r.json()
    assert "generated_at" in body
    assert "users" in body
    assert "content" in body
    assert "activity" in body
    assert "series" in body


async def test_dashboard_users_section_schema(app, user_factory):
    _authed_admin_app(app, user_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/dashboard")
    users = r.json()["users"]
    assert "total" in users
    assert "active_30d" in users
    assert "active_1h" in users
    assert "new_30d" in users


async def test_dashboard_activity_section_schema(app, user_factory):
    _authed_admin_app(app, user_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/dashboard")
    activity = r.json()["activity"]
    assert "audit_events_24h" in activity
    assert "logins_24h" in activity


async def test_dashboard_series_section_schema(app, user_factory):
    _authed_admin_app(app, user_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/dashboard")
    series = r.json()["series"]
    assert "daily_logins_14d" in series
    assert "daily_publications_14d" in series
    assert isinstance(series["daily_logins_14d"], list)
    assert isinstance(series["daily_publications_14d"], list)


async def test_top_files_excludes_photo_purged_event_type(app, user_factory):
    from app.api.deps import get_current_user, get_db

    user = user_factory(role="admin")
    captured_sql: list[str] = []

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        result = MagicMock()
        result.scalar_one = MagicMock(return_value=0)
        mapping_result = MagicMock()
        mapping_result.all = MagicMock(return_value=[])
        result.mappings = MagicMock(return_value=mapping_result)

        async def _capture_execute(stmt, *args, **kwargs):
            sql_text = str(stmt)
            captured_sql.append(sql_text)
            return result

        session.execute = _capture_execute
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/top-files")

    assert r.status_code == 200
    assert len(captured_sql) > 0
    top_files_sql = "\n".join(captured_sql)
    assert "photo_purged" not in top_files_sql
    assert "files.file_downloaded" in top_files_sql


async def test_top_files_allowed_event_types_in_query(app, user_factory):
    from app.api.deps import get_current_user, get_db

    user = user_factory(role="admin")
    captured_sql: list[str] = []

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        result = MagicMock()
        mapping_result = MagicMock()
        mapping_result.all = MagicMock(return_value=[])
        result.mappings = MagicMock(return_value=mapping_result)

        async def _capture_execute(stmt, *args, **kwargs):
            captured_sql.append(str(stmt))
            return result

        session.execute = _capture_execute
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        await ac.get("/api/v1/analytics/top-files")

    combined = "\n".join(captured_sql)
    for event in _ALLOWED_EVENTS:
        assert event in combined


async def test_top_files_response_schema(app, user_factory):
    from app.api.deps import get_current_user, get_db
    from datetime import UTC, datetime

    user = user_factory(role="admin")

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "resource_id": "res-1",
            "title": "Report.pdf",
            "downloads": 5,
            "last_download": datetime(2024, 1, 1, tzinfo=UTC),
        }[key]
        result = MagicMock()
        mapping_result = MagicMock()
        mapping_result.all = MagicMock(return_value=[row])
        result.mappings = MagicMock(return_value=mapping_result)
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/top-files")

    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert item["resource_id"] == "res-1"
    assert item["title"] == "Report.pdf"
    assert item["downloads"] == 5
    assert "last_download" in item


async def test_top_news_response_schema(app, user_factory):
    from app.api.deps import get_current_user, get_db
    from datetime import UTC, datetime
    import uuid

    user = user_factory(role="admin")
    news_id = str(uuid.uuid4())

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "id": news_id,
            "title": "Important Update",
            "view_count": 42,
            "published_at": datetime(2024, 3, 15, tzinfo=UTC),
        }[key]
        result = MagicMock()
        mapping_result = MagicMock()
        mapping_result.all = MagicMock(return_value=[row])
        result.mappings = MagicMock(return_value=mapping_result)
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/top-news")

    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert "id" in item
    assert "title" in item
    assert "view_count" in item
    assert "published_at" in item
    assert item["view_count"] == 42


async def test_top_articles_response_schema(app, user_factory):
    from app.api.deps import get_current_user, get_db
    from datetime import UTC, datetime
    import uuid

    user = user_factory(role="admin")
    article_id = str(uuid.uuid4())

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "id": article_id,
            "title": "How to Configure VPN",
            "section_title": "IT",
            "view_count": 100,
            "published_at": datetime(2024, 2, 1, tzinfo=UTC),
            "updated_at": datetime(2024, 4, 1, tzinfo=UTC),
        }[key]
        result = MagicMock()
        mapping_result = MagicMock()
        mapping_result.all = MagicMock(return_value=[row])
        result.mappings = MagicMock(return_value=mapping_result)
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/top-articles")

    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert "id" in item
    assert "title" in item
    assert "section_title" in item
    assert "view_count" in item
    assert "published_at" in item
    assert "updated_at" in item


async def test_departments_response_schema(app, user_factory):
    from app.api.deps import get_current_user, get_db

    user = user_factory(role="admin")

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "department": "Engineering",
            "total_users": 10,
            "active_users": 7,
            "events": 120,
        }[key]
        result = MagicMock()
        mapping_result = MagicMock()
        mapping_result.all = MagicMock(return_value=[row])
        result.mappings = MagicMock(return_value=mapping_result)
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/departments")

    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert item["department"] == "Engineering"
    assert item["total_users"] == 10
    assert item["active_users"] == 7
    assert item["events"] == 120


async def test_analytics_endpoints_require_admin_role(app, user_factory):
    from app.api.deps import get_current_user, get_db

    user = user_factory(role="reader")

    async def _fake_user():
        return user

    async def _fake_db():
        yield _make_db_session()

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/dashboard")
    assert r.status_code == 403
