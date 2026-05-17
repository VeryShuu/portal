"""Unit tests for app/api/news_categories.py — _load, _save, ensure_category_exists, routes."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("httpx", reason="httpx not installed")


def _make_user(role: str = "editor") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role=role, email="e@test.local")


def _build_app(user, db):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db
    from app.api.news_categories import router

    app = FastAPI()
    app.include_router(router)

    async def _user():
        return user

    async def _db():
        return db

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db

    from app.api.deps import require_editor

    app.dependency_overrides[require_editor] = _user
    return app


async def _get(app, url):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


async def _post(app, url, **kw):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, **kw)


async def _patch(app, url, **kw):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.patch(url, **kw)


async def _delete(app, url):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.delete(url)


class TestLoadCategories:
    def test_file_not_exists_returns_empty(self, tmp_path):
        from app.api.news_categories import _load

        with patch("app.api.news_categories._CATEGORIES_FILE", tmp_path / "nonexistent.json"):
            result = _load()

        assert result == []

    def test_invalid_json_returns_empty(self, tmp_path):
        from app.api.news_categories import _load

        bad_file = tmp_path / "categories.json"
        bad_file.write_text("NOT JSON", encoding="utf-8")
        with patch("app.api.news_categories._CATEGORIES_FILE", bad_file):
            result = _load()

        assert result == []

    def test_not_list_returns_empty(self, tmp_path):
        from app.api.news_categories import _load

        bad_file = tmp_path / "categories.json"
        bad_file.write_text('{"key": "value"}', encoding="utf-8")
        with patch("app.api.news_categories._CATEGORIES_FILE", bad_file):
            result = _load()

        assert result == []

    def test_legacy_string_format(self, tmp_path):
        from app.api.news_categories import _load

        cat_file = tmp_path / "categories.json"
        cat_file.write_text(json.dumps(["Tech", "Sport", ""]), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file):
            result = _load()

        assert len(result) == 2
        assert result[0].name == "Tech"
        assert result[1].name == "Sport"

    def test_dict_format(self, tmp_path):
        from app.api.news_categories import _load

        cat_file = tmp_path / "categories.json"
        data = [{"name": "Tech", "color": "#ff0000"}, {"name": "Sport", "color": "#00ff00"}]
        cat_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file):
            result = _load()

        assert len(result) == 2
        assert result[0].color == "#ff0000"

    def test_duplicate_names_deduped(self, tmp_path):
        from app.api.news_categories import _load

        cat_file = tmp_path / "categories.json"
        data = [{"name": "Tech", "color": "#ff0000"}, {"name": "TECH", "color": "#00ff00"}]
        cat_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file):
            result = _load()

        assert len(result) == 1


class TestEnsureCategoryExists:
    def test_empty_name_noop(self, tmp_path):
        from app.api.news_categories import ensure_category_exists

        with patch("app.api.news_categories._CATEGORIES_FILE", tmp_path / "cats.json"):
            ensure_category_exists("   ")

    def test_adds_new_category(self, tmp_path):
        from app.api.news_categories import _load, ensure_category_exists

        cat_file = tmp_path / "cats.json"
        cat_file.write_text("[]", encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file), \
             patch("app.api.news_categories._SETTINGS_DIR", tmp_path):
            ensure_category_exists("NewCat")
            result = _load()

        assert any(c.name == "NewCat" for c in result)

    def test_already_exists_noop(self, tmp_path):
        from app.api.news_categories import ensure_category_exists

        cat_file = tmp_path / "cats.json"
        cat_file.write_text(json.dumps([{"name": "Tech", "color": "#ff0000"}]), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file), \
             patch("app.api.news_categories._SETTINGS_DIR", tmp_path):
            ensure_category_exists("tech")

    def test_max_categories_noop(self, tmp_path):
        from app.api.news_categories import _MAX_CATEGORIES, ensure_category_exists

        items = [{"name": f"Cat{i}", "color": "#ff0000"} for i in range(_MAX_CATEGORIES)]
        cat_file = tmp_path / "cats.json"
        cat_file.write_text(json.dumps(items), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file), \
             patch("app.api.news_categories._SETTINGS_DIR", tmp_path):
            ensure_category_exists("NewOne")

    def test_save_error_swallowed(self, tmp_path):
        from app.api.news_categories import ensure_category_exists

        cat_file = tmp_path / "cats.json"
        cat_file.write_text("[]", encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file), \
             patch("app.api.news_categories._SETTINGS_DIR", tmp_path), \
             patch("app.api.news_categories._save", side_effect=OSError("disk full")):
            ensure_category_exists("NewCat")


class TestCategoriesRoutes:
    @pytest.mark.asyncio
    async def test_list_categories_empty(self, tmp_path):
        user = _make_user()
        db = AsyncMock()
        app = _build_app(user, db)

        with patch("app.api.news_categories._CATEGORIES_FILE", tmp_path / "nonexistent.json"):
            r = await _get(app, "/news-categories")

        assert r.status_code == 200
        assert r.json()["items"] == []

    @pytest.mark.asyncio
    async def test_list_categories_with_counts(self, tmp_path):
        user = _make_user()
        db = AsyncMock()

        row = MagicMock()
        row.cat = "Tech"
        row.cnt = 3
        db.execute.return_value = iter([row])

        app = _build_app(user, db)

        cat_file = tmp_path / "categories.json"
        cat_file.write_text(json.dumps([{"name": "Tech", "color": "#ff0000"}]), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file):
            r = await _get(app, "/news-categories")

        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Tech"
        assert data["items"][0]["news_count"] == 3

    @pytest.mark.asyncio
    async def test_add_category_success(self, tmp_path):
        user = _make_user()
        db = AsyncMock()
        app = _build_app(user, db)

        cat_file = tmp_path / "categories.json"
        cat_file.write_text("[]", encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file), \
             patch("app.api.news_categories._SETTINGS_DIR", tmp_path):
            r = await _post(app, "/news-categories", json={"name": "NewCat", "color": "#123456"})

        assert r.status_code == 201
        data = r.json()
        assert any(item["name"] == "NewCat" for item in data["items"])

    @pytest.mark.asyncio
    async def test_add_category_duplicate_409(self, tmp_path):
        user = _make_user()
        db = AsyncMock()
        app = _build_app(user, db)

        cat_file = tmp_path / "categories.json"
        cat_file.write_text(json.dumps([{"name": "Tech", "color": "#ff0000"}]), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file):
            r = await _post(app, "/news-categories", json={"name": "tech", "color": "#123456"})

        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_update_category_color_success(self, tmp_path):
        user = _make_user()
        db = AsyncMock()
        app = _build_app(user, db)

        cat_file = tmp_path / "categories.json"
        cat_file.write_text(json.dumps([{"name": "Tech", "color": "#ff0000"}]), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file), \
             patch("app.api.news_categories._SETTINGS_DIR", tmp_path):
            r = await _patch(app, "/news-categories/Tech/color", json={"color": "#aabbcc"})

        assert r.status_code == 200
        data = r.json()
        assert data["items"][0]["color"] == "#aabbcc"

    @pytest.mark.asyncio
    async def test_update_category_color_not_found(self, tmp_path):
        user = _make_user()
        db = AsyncMock()
        app = _build_app(user, db)

        cat_file = tmp_path / "categories.json"
        cat_file.write_text(json.dumps([{"name": "Tech", "color": "#ff0000"}]), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file):
            r = await _patch(app, "/news-categories/Unknown/color", json={"color": "#aabbcc"})

        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_category_success(self, tmp_path):
        user = _make_user()
        db = AsyncMock()
        app = _build_app(user, db)

        cat_file = tmp_path / "categories.json"
        cat_file.write_text(json.dumps([{"name": "Tech", "color": "#ff0000"}]), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file), \
             patch("app.api.news_categories._SETTINGS_DIR", tmp_path):
            r = await _delete(app, "/news-categories/Tech")

        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_delete_category_not_found(self, tmp_path):
        user = _make_user()
        db = AsyncMock()
        app = _build_app(user, db)

        cat_file = tmp_path / "categories.json"
        cat_file.write_text(json.dumps([{"name": "Tech", "color": "#ff0000"}]), encoding="utf-8")

        with patch("app.api.news_categories._CATEGORIES_FILE", cat_file):
            r = await _delete(app, "/news-categories/Unknown")

        assert r.status_code == 404
