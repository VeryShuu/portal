"""Unit-тесты для api/search.py.

Покрытие:
- _escape_like: экранирование спецсимволов LIKE
- GET /search: 401 без аутентификации, валидация q (min_length)
- GET /search?type=...: фильтрация по типу
- GET /search/suggest: 401 без аутентификации
- Сортировка результатов по created_at
"""

from __future__ import annotations

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
