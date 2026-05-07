"""
Unit-тесты для модуля news_categories.

Покрытие:
- _load: нет файла → [], повреждённый JSON → [], не-список → [], дубликаты (case-insensitive), пустые строки
- _save: атомарная запись через tempfile + os.replace
- GET /news-categories: 401 без сессии, 200 со списком
- POST /news-categories: 201 editor, 403 reader, 409 дубликат, 422 слишком много
- DELETE /news-categories/{name}: 200 editor, 403 reader, 404 не найдено, case-insensitive match
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


# ── helpers ───────────────────────────────────────────────────────────────────


def _authed_app(app, user_factory, role: str = "editor"):
    from app.api.deps import get_current_user, get_db

    user = user_factory(role=role)

    async def _fake_user():
        return user

    async def _fake_db():
        session = AsyncMock()
        session.execute.return_value = []
        yield session

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db
    return app


def _make_client(app):
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": "http://test", "x-xsrf-token": "tok"},
        cookies={"XSRF-TOKEN": "tok"},
    )


# ── _load ─────────────────────────────────────────────────────────────────────


class TestLoad:
    def test_no_file_returns_empty(self, tmp_path):
        from app.api import news_categories as nc

        missing = tmp_path / "news_categories.json"
        with patch.object(nc, "_CATEGORIES_FILE", missing):
            result = nc._load()
        assert result == []

    def test_corrupted_json_returns_empty(self, tmp_path):
        from app.api import news_categories as nc

        f = tmp_path / "news_categories.json"
        f.write_text("not-json", encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            result = nc._load()
        assert result == []

    def test_non_list_returns_empty(self, tmp_path):
        from app.api import news_categories as nc

        f = tmp_path / "news_categories.json"
        f.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            result = nc._load()
        assert result == []

    def test_valid_list_returned(self, tmp_path):
        from app.api import news_categories as nc

        f = tmp_path / "news_categories.json"
        f.write_text(json.dumps(["HR", "IT", "Finance"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            result = nc._load()
        assert [c.name for c in result] == ["HR", "IT", "Finance"]

    def test_duplicates_case_insensitive_removed(self, tmp_path):
        from app.api import news_categories as nc

        f = tmp_path / "news_categories.json"
        f.write_text(json.dumps(["HR", "hr", "Hr", "IT"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            result = nc._load()
        assert [c.name for c in result] == ["HR", "IT"]

    def test_empty_strings_skipped(self, tmp_path):
        from app.api import news_categories as nc

        f = tmp_path / "news_categories.json"
        f.write_text(json.dumps(["HR", "", "  ", "IT"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            result = nc._load()
        assert [c.name for c in result] == ["HR", "IT"]

    def test_non_string_items_skipped(self, tmp_path):
        from app.api import news_categories as nc

        f = tmp_path / "news_categories.json"
        f.write_text(json.dumps(["HR", 42, None, "IT"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            result = nc._load()
        assert [c.name for c in result] == ["HR", "IT"]

    def test_whitespace_stripped(self, tmp_path):
        from app.api import news_categories as nc

        f = tmp_path / "news_categories.json"
        f.write_text(json.dumps(["  HR  ", " IT "]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            result = nc._load()
        assert [c.name for c in result] == ["HR", "IT"]

    def test_dict_format_loaded(self, tmp_path):
        from app.api import news_categories as nc

        f = tmp_path / "news_categories.json"
        data = [{"name": "HR", "color": "#FF0000"}, {"name": "IT", "color": "#00FF00"}]
        f.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            result = nc._load()
        assert result[0].name == "HR"
        assert result[0].color == "#FF0000"
        assert result[1].name == "IT"
        assert result[1].color == "#00FF00"

    def test_default_color_assigned_for_string_format(self, tmp_path):
        from app.api import news_categories as nc

        f = tmp_path / "news_categories.json"
        f.write_text(json.dumps(["HR"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            result = nc._load()
        assert result[0].color == nc._DEFAULT_COLOR


# ── _save ─────────────────────────────────────────────────────────────────────


class TestSave:
    def test_saves_to_file(self, tmp_path):
        from app.api import news_categories as nc
        from app.api.news_categories import NewsCategory

        settings_dir = tmp_path / "settings"
        target_file = settings_dir / "news_categories.json"
        items = [
            NewsCategory(name="HR", color="#6B7AE8"),
            NewsCategory(name="IT", color="#6B7AE8"),
        ]
        with patch.object(nc, "_SETTINGS_DIR", settings_dir), \
             patch.object(nc, "_CATEGORIES_FILE", target_file):
            nc._save(items)

        data = json.loads(target_file.read_text(encoding="utf-8"))
        assert data == [
            {"name": "HR", "color": "#6B7AE8"},
            {"name": "IT", "color": "#6B7AE8"},
        ]

    def test_creates_dir_if_missing(self, tmp_path):
        from app.api import news_categories as nc

        settings_dir = tmp_path / "new_dir"
        target_file = settings_dir / "news_categories.json"
        assert not settings_dir.exists()
        with patch.object(nc, "_SETTINGS_DIR", settings_dir), \
             patch.object(nc, "_CATEGORIES_FILE", target_file):
            nc._save([])

        assert settings_dir.exists()

    def test_atomic_write_via_replace(self, tmp_path):
        from app.api import news_categories as nc
        from app.api.news_categories import NewsCategory

        settings_dir = tmp_path / "settings"
        target_file = settings_dir / "news_categories.json"
        replaced_paths = []

        original_replace = os.replace

        def _spy_replace(src, dst):
            replaced_paths.append((src, dst))
            return original_replace(src, dst)

        with patch.object(nc, "_SETTINGS_DIR", settings_dir), \
             patch.object(nc, "_CATEGORIES_FILE", target_file), \
             patch("app.api.news_categories.os.replace", side_effect=_spy_replace):
            nc._save([NewsCategory(name="Finance", color="#6B7AE8")])

        assert len(replaced_paths) == 1
        _, dst = replaced_paths[0]
        assert Path(dst) == target_file


# ── GET /news-categories ──────────────────────────────────────────────────────


class TestListCategories:
    async def test_unauthenticated_returns_401(self, client):
        r = await client.get("/api/v1/news-categories")
        assert r.status_code == 401

    async def test_reader_can_list(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="reader")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        f.write_text(json.dumps(["HR", "IT"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            async with _make_client(app) as ac:
                r = await ac.get("/api/v1/news-categories")

        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        assert items[0]["name"] == "HR"
        assert items[1]["name"] == "IT"
        assert "color" in items[0]
        assert "news_count" in items[0]

    async def test_empty_list_when_no_file(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="reader")
        from app.api import news_categories as nc

        missing = tmp_path / "missing.json"
        with patch.object(nc, "_CATEGORIES_FILE", missing):
            async with _make_client(app) as ac:
                r = await ac.get("/api/v1/news-categories")

        assert r.status_code == 200
        assert r.json()["items"] == []


# ── POST /news-categories ─────────────────────────────────────────────────────


class TestAddCategory:
    async def test_reader_forbidden(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="reader")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        f.write_text(json.dumps([]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "HR"})

        assert r.status_code == 403

    async def test_editor_creates_category(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps([]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "HR"})

        assert r.status_code == 201
        names = [item["name"] for item in r.json()["items"]]
        assert "HR" in names

    async def test_editor_creates_category_with_color(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps([]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "HR", "color": "#FF0000"})

        assert r.status_code == 201
        item = next(i for i in r.json()["items"] if i["name"] == "HR")
        assert item["color"] == "#FF0000"

    async def test_admin_creates_category(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="admin")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps([]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "Finance"})

        assert r.status_code == 201

    async def test_duplicate_returns_409(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps(["HR"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "HR"})

        assert r.status_code == 409

    async def test_duplicate_case_insensitive_returns_409(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps(["HR"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "hr"})

        assert r.status_code == 409

    async def test_too_many_categories_returns_400(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        existing = [f"cat{i}" for i in range(nc._MAX_CATEGORIES)]
        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps(existing), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "NewCat"})

        assert r.status_code == 400

    async def test_empty_name_returns_422(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps([]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "   "})

        assert r.status_code == 422

    async def test_name_too_long_returns_422(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps([]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "x" * 101})

        assert r.status_code == 422

    async def test_invalid_color_returns_422(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps([]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.post("/api/v1/news-categories", json={"name": "HR", "color": "red"})

        assert r.status_code == 422


# ── DELETE /news-categories/{name} ────────────────────────────────────────────


class TestDeleteCategory:
    async def test_reader_forbidden(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="reader")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        f.write_text(json.dumps(["HR"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f):
            async with _make_client(app) as ac:
                r = await ac.delete("/api/v1/news-categories/HR")

        assert r.status_code == 403

    async def test_editor_deletes_category(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps(["HR", "IT"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.delete("/api/v1/news-categories/HR")

        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert names == ["IT"]

    async def test_delete_case_insensitive(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps(["HR", "IT"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.delete("/api/v1/news-categories/hr")

        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert "HR" not in names

    async def test_not_found_returns_404(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="editor")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps(["IT"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.delete("/api/v1/news-categories/HR")

        assert r.status_code == 404

    async def test_delete_leaves_other_categories(self, app, user_factory, tmp_path):
        _authed_app(app, user_factory, role="admin")
        from app.api import news_categories as nc

        f = tmp_path / "nc.json"
        settings_dir = tmp_path
        f.write_text(json.dumps(["HR", "IT", "Finance"]), encoding="utf-8")
        with patch.object(nc, "_CATEGORIES_FILE", f), \
             patch.object(nc, "_SETTINGS_DIR", settings_dir):
            async with _make_client(app) as ac:
                r = await ac.delete("/api/v1/news-categories/IT")

        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert "IT" not in names
        assert "HR" in names
        assert "Finance" in names
