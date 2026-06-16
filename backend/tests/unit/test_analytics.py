from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

_ALLOWED_EVENTS = {
    "files.file_downloaded",
    "kb.file_download",
    "photos.photo_downloaded",
    "kb.article_exported_pdf",
    "kb.article_exported_docx",
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
    row.wau_7d = value
    row.mau_30d = value
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
    from datetime import UTC, datetime

    from app.api.deps import get_current_user, get_db

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
    import uuid
    from datetime import UTC, datetime

    from app.api.deps import get_current_user, get_db

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
    import uuid
    from datetime import UTC, datetime

    from app.api.deps import get_current_user, get_db

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


async def test_top_files_query_excludes_dead_news_exported_event(app, user_factory):
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
    assert "news.exported" not in combined


async def test_top_links_query_filters_links_visited_event(app, user_factory):
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
        r = await ac.get("/api/v1/analytics/top-links")

    assert r.status_code == 200
    combined = "\n".join(captured_sql)
    assert "links.visited" in combined


async def test_top_links_response_schema(app, user_factory):
    from datetime import UTC, datetime

    from app.api.deps import get_current_user, get_db

    user = user_factory(role="admin")

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "resource_id": "link-1",
            "title": "Confluence",
            "clicks": 8,
            "unique_users": 3,
            "last_click": datetime(2024, 1, 1, tzinfo=UTC),
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
        r = await ac.get("/api/v1/analytics/top-links")

    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert item["resource_id"] == "link-1"
    assert item["title"] == "Confluence"
    assert item["clicks"] == 8
    assert item["unique_users"] == 3
    assert "last_click" in item


async def test_top_links_requires_admin_role(app, user_factory):
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
        r = await ac.get("/api/v1/analytics/top-links")
    assert r.status_code == 403


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


async def test_stale_content_response_schema(app, user_factory):
    import uuid
    from datetime import UTC, datetime

    from app.api.deps import get_current_user, get_db

    user = user_factory(role="admin")
    item_id = str(uuid.uuid4())

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "kind": "kb",
            "id": item_id,
            "title": "Forgotten article",
            "view_count": 0,
            "updated_at": datetime(2023, 1, 1, tzinfo=UTC),
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
        r = await ac.get("/api/v1/analytics/stale-content")

    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert item["kind"] == "kb"
    assert item["id"] == item_id
    assert item["title"] == "Forgotten article"
    assert item["view_count"] == 0
    assert "updated_at" in item


async def test_feedback_stats_response_schema(app, user_factory):
    from app.api.deps import get_current_user, get_db

    user = user_factory(role="admin")

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "total": 5,
            "open": 2,
            "in_progress": 1,
            "closed": 2,
            "avg_first_response_seconds": 3600.0,
        }[key]
        result = MagicMock()
        mapping_result = MagicMock()
        mapping_result.one = MagicMock(return_value=row)
        result.mappings = MagicMock(return_value=mapping_result)
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/feedback")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["open"] == 2
    assert body["in_progress"] == 1
    assert body["closed"] == 2
    assert body["avg_first_response_seconds"] == 3600.0


async def test_feedback_stats_null_avg_response(app, user_factory):
    from app.api.deps import get_current_user, get_db

    user = user_factory(role="admin")

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "total": 0,
            "open": 0,
            "in_progress": 0,
            "closed": 0,
            "avg_first_response_seconds": None,
        }[key]
        result = MagicMock()
        mapping_result = MagicMock()
        mapping_result.one = MagicMock(return_value=row)
        result.mappings = MagicMock(return_value=mapping_result)
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/feedback")

    assert r.status_code == 200
    assert r.json()["avg_first_response_seconds"] is None


async def test_resource_trend_response_schema(app, user_factory):
    from datetime import date

    from app.api.deps import get_current_user, get_db

    user = user_factory(role="admin")

    async def _fake_user():
        return user

    async def _fake_db():
        session = MagicMock()
        result = MagicMock()
        result.all = MagicMock(return_value=[(date(2024, 1, 1), 5), (date(2024, 1, 2), 8)])
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/resource-trend?resource_id=link-1&kind=link")

    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 2
    assert items[0]["day"] == "2024-01-01"
    assert items[0]["count"] == 5


async def test_resource_trend_rejects_invalid_kind(app, user_factory):
    _authed_admin_app(app, user_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/resource-trend?resource_id=x&kind=bogus")
    assert r.status_code == 422


async def test_export_csv_departments(app, user_factory):
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
        r = await ac.get("/api/v1/analytics/export?dataset=departments&format=csv")

    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    assert "Engineering" in r.text


async def test_export_xlsx_departments(app, user_factory):
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
        r = await ac.get("/api/v1/analytics/export?dataset=departments&format=xlsx")

    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"


async def test_export_rejects_unknown_dataset(app, user_factory):
    _authed_admin_app(app, user_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/api/v1/analytics/export?dataset=bogus&format=csv")
    assert r.status_code == 422
