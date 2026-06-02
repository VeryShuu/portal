"""Unit-тесты для api/search.py.

Покрытие:
- _escape_like: экранирование спецсимволов LIKE
- GET /search: 401 без аутентификации, валидация q (min_length)
- GET /search?type=...: фильтрация по типу
- GET /search/suggest: 401 без аутентификации
- Сортировка результатов по created_at
- Single-type branches: article / news / link / user
- Multi-type filters: from_date / to_date / author_id / department
- Role-targeting: reader vs editor/admin
- ACL hooks: apply_article_visibility, filter_accessible_articles
- Suggest: dedup, max-10, KB→News order
- type=invalid falls back to all types
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


# ── _escape_like ──────────────────────────────────────────────────────────────


class TestEscapeLike:
    def test_percent_escaped(self):
        from app.api.search import _escape_like

        assert _escape_like("100%") == r"100\%"

    def test_underscore_escaped(self):
        from app.api.search import _escape_like

        assert _escape_like("file_name") == r"file\_name"

    def test_backslash_escaped(self):
        from app.api.search import _escape_like

        result = _escape_like("path\\to")
        assert "\\\\" in result

    def test_plain_string_unchanged(self):
        from app.api.search import _escape_like

        assert _escape_like("hello world") == "hello world"

    def test_combined(self):
        from app.api.search import _escape_like

        result = _escape_like("100%_off\\deal")
        assert r"\%" in result
        assert r"\_" in result
        assert "\\\\" in result

    def test_empty_string(self):
        from app.api.search import _escape_like

        assert _escape_like("") == ""

    def test_cyrillic_unchanged(self):
        from app.api.search import _escape_like

        assert _escape_like("тест запрос") == "тест запрос"


# ── GET /search auth ──────────────────────────────────────────────────────────


class TestSearchEndpointAuth:
    async def test_unauthenticated_gets_401(self, client):
        r = await client.get("/api/v1/search?q=test")
        assert r.status_code == 401

    async def test_empty_query_gets_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.get("/api/v1/search?q=")
        assert r.status_code == 422

    async def test_query_too_long_gets_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.get(f"/api/v1/search?q={'x' * 201}")
        assert r.status_code == 422

    async def test_invalid_limit_gets_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.get("/api/v1/search?q=test&limit=51")
        assert r.status_code == 422

    async def test_valid_query_returns_search_response(self, authed_client_factory):

        ac, _ = authed_client_factory(role="reader")

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[])
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_result.scalar_one = MagicMock(return_value=0)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.api.search.filter_accessible_articles", new_callable=AsyncMock, return_value=[]
            ),
        ):
            r = await ac.get("/api/v1/search?q=hello")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert body["query"] == "hello"

    async def test_multi_type_total_is_sum_of_per_type_counts(
        self, authed_client_factory, monkeypatch
    ):
        """Multi-type total must reflect true count across all types,
        not just the size of the merged window (offset+limit).
        """
        ac, _ = authed_client_factory(role="reader")

        # Per-type COUNT(*) we will report; len(results) on the page would be 0
        # because each type returns no items in this synthetic setup.
        per_type_counts = iter([42, 17, 5, 9])  # article, news, link, user

        empty_result = MagicMock()
        empty_result.all = MagicMock(return_value=[])
        empty_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        async def fake_execute(stmt):
            stmt_str = str(stmt)
            res = MagicMock()
            res.all = MagicMock(return_value=[])
            res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            if "count(" in stmt_str.lower():
                res.scalar_one = MagicMock(return_value=next(per_type_counts))
            else:
                res.scalar_one = MagicMock(return_value=0)
            return res

        from app.api import deps as api_deps

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        from app.main import app as fastapi_app

        fastapi_app.dependency_overrides[api_deps.get_db] = fake_get_db

        with patch(
            "app.api.search.apply_article_visibility",
            new=AsyncMock(side_effect=lambda stmt, u, d: stmt),
        ):
            r = await ac.get("/api/v1/search?q=hello&limit=10&offset=0")

        fastapi_app.dependency_overrides.pop(api_deps.get_db, None)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 42 + 17 + 5 + 9
        assert body["items"] == []


class TestSearchSuggestEndpoint:
    async def test_unauthenticated_gets_401(self, client):
        r = await client.get("/api/v1/search/suggest?q=test")
        assert r.status_code == 401

    async def test_empty_query_gets_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.get("/api/v1/search/suggest?q=")
        assert r.status_code == 422

    async def test_valid_suggest_returns_list(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_result.__iter__ = MagicMock(return_value=iter([]))

        with patch(
            "app.api.search.filter_accessible_articles", new_callable=AsyncMock, return_value=[]
        ):
            r = await ac.get("/api/v1/search/suggest?q=test")
        assert r.status_code == 200
        body = r.json()
        assert "suggestions" in body
        assert isinstance(body["suggestions"], list)


# ── Sorting logic (pure Python) ───────────────────────────────────────────────


class TestSearchResultSorting:
    def test_sort_by_created_at_descending(self):
        from app.api.search import _DATETIME_MIN_UTC
        from app.schemas.kb import SearchResultItem

        now = datetime.now(UTC)
        old = datetime(2020, 1, 1, tzinfo=UTC)

        items = [
            SearchResultItem(
                type="news", id="1", title="Old", snippet="", url="/a", created_at=old
            ),
            SearchResultItem(
                type="news", id="2", title="New", snippet="", url="/b", created_at=now
            ),
        ]
        items.sort(key=lambda r: r.created_at or _DATETIME_MIN_UTC, reverse=True)
        assert items[0].id == "2"
        assert items[1].id == "1"

    def test_sort_with_none_created_at(self):
        from app.api.search import _DATETIME_MIN_UTC
        from app.schemas.kb import SearchResultItem

        now = datetime.now(UTC)

        items = [
            SearchResultItem(
                type="news", id="1", title="No date", snippet="", url="/a", created_at=None
            ),
            SearchResultItem(
                type="news", id="2", title="With date", snippet="", url="/b", created_at=now
            ),
        ]
        items.sort(key=lambda r: r.created_at or _DATETIME_MIN_UTC, reverse=True)
        assert items[0].id == "2"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _empty_db_result():
    res = MagicMock()
    res.scalar_one = MagicMock(return_value=0)
    res.all = MagicMock(return_value=[])
    res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    res.__iter__ = MagicMock(return_value=iter([]))
    return res


def _make_link_mock(url="https://example.com"):
    lnk = MagicMock()
    lnk.id = _uuid.uuid4()
    lnk.title = "Example Link"
    lnk.description = "A link description"
    lnk.url = url
    lnk.created_at = datetime.now(UTC)
    return lnk


def _override_db(fastapi_app, api_deps, fake_get_db):
    fastapi_app.dependency_overrides[api_deps.get_db] = fake_get_db


def _restore_db(fastapi_app, api_deps):
    fastapi_app.dependency_overrides.pop(api_deps.get_db, None)


# ── Single-type: article ───────────────────────────────────────────────────────


class TestSingleTypeArticle:
    async def test_returns_article_items_and_url(self, authed_client_factory, kb_article_factory):
        ac, _ = authed_client_factory(role="reader")
        article = kb_article_factory(status="published")

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = _empty_db_result()
            if call_n == 1:
                res.scalar_one = MagicMock(return_value=1)
            else:
                res.all = MagicMock(return_value=[(article, "match snippet")])
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        with patch(
            "app.api.search.apply_article_visibility",
            new=AsyncMock(side_effect=lambda s, u, d: s),
        ):
            r = await ac.get("/api/v1/search?q=hello&type=article")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["query"] == "hello"
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["type"] == "article"
        assert item["url"] == f"/kb/articles/{article.id}"
        assert item["title"] == article.title
        assert item["snippet"] == "match snippet"

    async def test_apply_article_visibility_called_twice(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(return_value=_empty_db_result())
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        visibility_mock = AsyncMock(side_effect=lambda s, u, d: s)
        with patch("app.api.search.apply_article_visibility", new=visibility_mock):
            r = await ac.get("/api/v1/search?q=test&type=article")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        assert visibility_mock.call_count == 2

    async def test_article_date_and_author_filters(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(return_value=_empty_db_result())
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        author_id = str(_uuid.uuid4())
        with patch(
            "app.api.search.apply_article_visibility",
            new=AsyncMock(side_effect=lambda s, u, d: s),
        ):
            r = await ac.get(
                f"/api/v1/search?q=test&type=article"
                f"&from_date=2024-01-01T00:00:00Z"
                f"&to_date=2024-12-31T23:59:59Z"
                f"&author_id={author_id}"
            )

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    async def test_article_empty_result(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(return_value=_empty_db_result())
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        with patch(
            "app.api.search.apply_article_visibility",
            new=AsyncMock(side_effect=lambda s, u, d: s),
        ):
            r = await ac.get("/api/v1/search?q=test&type=article&offset=5&limit=10")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        assert r.json()["items"] == []


# ── Single-type: news ─────────────────────────────────────────────────────────


class TestSingleTypeNews:
    async def test_returns_news_items_and_url(self, authed_client_factory, news_factory):
        ac, _ = authed_client_factory(role="editor")
        news = news_factory(status="published")

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = _empty_db_result()
            if call_n == 1:
                res.scalar_one = MagicMock(return_value=1)
            else:
                res.all = MagicMock(return_value=[(news, "news snippet")])
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        r = await ac.get("/api/v1/search?q=hello&type=news")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["type"] == "news"
        assert item["url"] == f"/news/{news.id}"
        assert item["title"] == news.title
        assert item["snippet"] == "news snippet"

    async def test_reader_role_calls_news_targeting(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(return_value=_empty_db_result())
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        targeting_mock = MagicMock(return_value=[])
        with patch("app.api.search.news_targeting_conditions", new=targeting_mock):
            r = await ac.get("/api/v1/search?q=test&type=news")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        targeting_mock.assert_called_once()

    async def test_editor_role_skips_news_targeting(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(return_value=_empty_db_result())
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        targeting_mock = MagicMock(return_value=[])
        with patch("app.api.search.news_targeting_conditions", new=targeting_mock):
            r = await ac.get("/api/v1/search?q=test&type=news")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        targeting_mock.assert_not_called()

    async def test_admin_role_skips_news_targeting(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(return_value=_empty_db_result())
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        targeting_mock = MagicMock(return_value=[])
        with patch("app.api.search.news_targeting_conditions", new=targeting_mock):
            r = await ac.get("/api/v1/search?q=test&type=news")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        targeting_mock.assert_not_called()

    async def test_news_date_author_department_filters(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(return_value=_empty_db_result())
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        author_id = str(_uuid.uuid4())
        r = await ac.get(
            f"/api/v1/search?q=test&type=news"
            f"&from_date=2024-01-01T00:00:00Z"
            f"&to_date=2024-12-31T23:59:59Z"
            f"&author_id={author_id}"
            f"&department=Engineering"
        )

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []


# ── Single-type: link ─────────────────────────────────────────────────────────


class TestSingleTypeLink:
    async def test_returns_link_items_and_url(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        lnk = _make_link_mock(url="https://portal.example.com/tool")

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = _empty_db_result()
            if call_n == 1:
                res.scalar_one = MagicMock(return_value=1)
            else:
                res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[lnk])))
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        r = await ac.get("/api/v1/search?q=tool&type=link")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["type"] == "link"
        assert item["url"] == "https://portal.example.com/tool"
        assert item["title"] == lnk.title
        assert item["snippet"] == lnk.description

    async def test_link_empty_result(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(return_value=_empty_db_result())
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        r = await ac.get("/api/v1/search?q=nothing&type=link")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["items"] == []


# ── Single-type: user ─────────────────────────────────────────────────────────


class TestSingleTypeUser:
    async def test_returns_user_items_and_url(self, authed_client_factory, user_factory):
        ac, _ = authed_client_factory(role="reader")
        found_user = user_factory(role="reader", position="Engineer", department="IT")

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = _empty_db_result()
            if call_n == 1:
                res.scalar_one = MagicMock(return_value=1)
            else:
                res.scalars = MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[found_user]))
                )
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        r = await ac.get("/api/v1/search?q=engineer&type=user")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["type"] == "user"
        assert item["url"] == f"/users/{found_user.id}"
        assert item["title"] == found_user.full_name

    async def test_user_snippet_combines_position_and_department(
        self, authed_client_factory, user_factory
    ):
        ac, _ = authed_client_factory(role="reader")
        found_user = user_factory(role="reader", position="Senior Dev", department="Backend")

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = _empty_db_result()
            if call_n == 1:
                res.scalar_one = MagicMock(return_value=1)
            else:
                res.scalars = MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[found_user]))
                )
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        r = await ac.get("/api/v1/search?q=dev&type=user")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        item = r.json()["items"][0]
        assert "Senior Dev" in item["snippet"]
        assert "Backend" in item["snippet"]

    async def test_user_department_filter(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(return_value=_empty_db_result())
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        r = await ac.get("/api/v1/search?q=test&type=user&department=Engineering")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        assert r.json()["total"] == 0

    async def test_user_empty_position_and_department(self, authed_client_factory, user_factory):
        ac, _ = authed_client_factory(role="reader")
        found_user = user_factory(role="reader", position=None, department=None)

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = _empty_db_result()
            if call_n == 1:
                res.scalar_one = MagicMock(return_value=1)
            else:
                res.scalars = MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[found_user]))
                )
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        r = await ac.get("/api/v1/search?q=test&type=user")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["snippet"] == ""


# ── type=invalid falls back to all types ──────────────────────────────────────


class TestInvalidTypeFallback:
    async def test_invalid_type_uses_multi_type_path(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        with patch(
            "app.api.search.apply_article_visibility",
            new=AsyncMock(side_effect=lambda s, u, d: s),
        ):
            r = await ac.get("/api/v1/search?q=hello&type=invalid")

        assert r.status_code == 200
        body = r.json()
        assert body["query"] == "hello"
        assert body["total"] == 0
        assert body["items"] == []

    async def test_none_type_uses_multi_type_path(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        with patch(
            "app.api.search.apply_article_visibility",
            new=AsyncMock(side_effect=lambda s, u, d: s),
        ):
            r = await ac.get("/api/v1/search?q=hello")

        assert r.status_code == 200
        assert r.json()["total"] == 0


# ── Multi-type filters ────────────────────────────────────────────────────────


class TestMultiTypeFilters:
    async def test_multi_type_with_date_author_department(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        author_id = str(_uuid.uuid4())
        with patch(
            "app.api.search.apply_article_visibility",
            new=AsyncMock(side_effect=lambda s, u, d: s),
        ):
            r = await ac.get(
                f"/api/v1/search?q=hello"
                f"&from_date=2024-01-01T00:00:00Z"
                f"&to_date=2024-12-31T23:59:59Z"
                f"&author_id={author_id}"
                f"&department=IT"
            )

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    async def test_multi_type_offset_slices_results(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        with patch(
            "app.api.search.apply_article_visibility",
            new=AsyncMock(side_effect=lambda s, u, d: s),
        ):
            r = await ac.get("/api/v1/search?q=hello&offset=5&limit=5")

        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []

    async def test_multi_type_reader_news_targeting_applied(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        targeting_mock = MagicMock(return_value=[])
        with (
            patch(
                "app.api.search.apply_article_visibility",
                new=AsyncMock(side_effect=lambda s, u, d: s),
            ),
            patch("app.api.search.news_targeting_conditions", new=targeting_mock),
        ):
            r = await ac.get("/api/v1/search?q=test")

        assert r.status_code == 200
        targeting_mock.assert_called()

    async def test_multi_type_editor_news_targeting_skipped(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")

        targeting_mock = MagicMock(return_value=[])
        with (
            patch(
                "app.api.search.apply_article_visibility",
                new=AsyncMock(side_effect=lambda s, u, d: s),
            ),
            patch("app.api.search.news_targeting_conditions", new=targeting_mock),
        ):
            r = await ac.get("/api/v1/search?q=test")

        assert r.status_code == 200
        targeting_mock.assert_not_called()


# ── Suggest: extended coverage ────────────────────────────────────────────────


class TestSuggestBehavior:
    async def test_suggest_kb_articles_appear_before_news(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")

        kb_article = MagicMock()
        kb_article.title = "KB Article Title"

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = MagicMock()
            if call_n == 1:
                res.scalars = MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[kb_article]))
                )
            else:
                res.__iter__ = MagicMock(return_value=iter([("News Title",)]))
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        with patch(
            "app.api.search.filter_accessible_articles",
            new=AsyncMock(return_value=[kb_article]),
        ):
            r = await ac.get("/api/v1/search/suggest?q=test")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        body = r.json()
        suggestions = body["suggestions"]
        assert "KB Article Title" in suggestions
        assert "News Title" in suggestions
        assert suggestions.index("KB Article Title") < suggestions.index("News Title")

    async def test_suggest_deduplicates_news_title_already_in_kb(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")

        shared_title = "Shared Topic"
        kb_article = MagicMock()
        kb_article.title = shared_title

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = MagicMock()
            if call_n == 1:
                res.scalars = MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[kb_article]))
                )
            else:
                res.__iter__ = MagicMock(return_value=iter([(shared_title,), ("Unique News",)]))
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        with patch(
            "app.api.search.filter_accessible_articles",
            new=AsyncMock(return_value=[kb_article]),
        ):
            r = await ac.get("/api/v1/search/suggest?q=shared")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        suggestions = r.json()["suggestions"]
        assert suggestions.count(shared_title) == 1
        assert "Unique News" in suggestions

    async def test_suggest_capped_at_ten(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")

        kb_articles = [MagicMock(title=f"KB {i}") for i in range(5)]

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = MagicMock()
            if call_n == 1:
                res.scalars = MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=kb_articles))
                )
            else:
                res.__iter__ = MagicMock(return_value=iter([(f"News {i}",) for i in range(10)]))
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        with patch(
            "app.api.search.filter_accessible_articles",
            new=AsyncMock(return_value=kb_articles),
        ):
            r = await ac.get("/api/v1/search/suggest?q=test")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        assert len(r.json()["suggestions"]) <= 10

    async def test_suggest_reader_applies_news_targeting(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = MagicMock()
            if call_n == 1:
                res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            else:
                res.__iter__ = MagicMock(return_value=iter([]))
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        targeting_mock = MagicMock(return_value=[])
        with (
            patch(
                "app.api.search.filter_accessible_articles",
                new=AsyncMock(return_value=[]),
            ),
            patch("app.api.search.news_targeting_conditions", new=targeting_mock),
        ):
            r = await ac.get("/api/v1/search/suggest?q=test")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        targeting_mock.assert_called_once()

    async def test_suggest_editor_skips_news_targeting(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = MagicMock()
            if call_n == 1:
                res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            else:
                res.__iter__ = MagicMock(return_value=iter([]))
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        targeting_mock = MagicMock(return_value=[])
        with (
            patch(
                "app.api.search.filter_accessible_articles",
                new=AsyncMock(return_value=[]),
            ),
            patch("app.api.search.news_targeting_conditions", new=targeting_mock),
        ):
            r = await ac.get("/api/v1/search/suggest?q=test")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        targeting_mock.assert_not_called()

    async def test_suggest_empty_results(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        call_n = 0

        async def fake_execute(stmt):
            nonlocal call_n
            call_n += 1
            res = MagicMock()
            if call_n == 1:
                res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            else:
                res.__iter__ = MagicMock(return_value=iter([]))
            return res

        from app.api import deps as api_deps
        from app.main import app as fastapi_app

        async def fake_get_db():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=fake_execute)
            yield db

        _override_db(fastapi_app, api_deps, fake_get_db)

        with patch(
            "app.api.search.filter_accessible_articles",
            new=AsyncMock(return_value=[]),
        ):
            r = await ac.get("/api/v1/search/suggest?q=nothing")

        _restore_db(fastapi_app, api_deps)

        assert r.status_code == 200
        assert r.json()["suggestions"] == []
