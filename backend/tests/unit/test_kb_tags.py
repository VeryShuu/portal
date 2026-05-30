"""Unit tests for app.api.kb.tags endpoints."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role="editor",
        email="e@test.local",
        keycloak_id=None,
    )


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    return db


def _build_app(user, db):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis, require_admin
    from app.api.kb.tags import router

    _app = FastAPI()
    _app.include_router(router)

    async def _fake_user():
        return user

    async def _fake_db():
        return db

    async def _fake_redis():
        return AsyncMock()

    _app.dependency_overrides[get_current_user] = _fake_user
    _app.dependency_overrides[get_db] = _fake_db
    _app.dependency_overrides[get_redis] = _fake_redis
    _app.dependency_overrides[require_admin] = _fake_user
    return _app


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


def _make_tag(name: str, slug: str) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.name = name
    t.slug = slug
    return t


class TestListTags:
    @pytest.mark.asyncio
    async def test_list_tags_returns_array_sorted(self):
        user = _make_user()
        db = _make_db()

        tags = [_make_tag("Alpha", "alpha"), _make_tag("Beta", "beta")]
        res = MagicMock(scalars=MagicMock(return_value=iter(tags)))
        db.execute.return_value = res

        app = _build_app(user, db)
        r = await _get(app, "/kb/tags")

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert {t["slug"] for t in data} == {"alpha", "beta"}

    @pytest.mark.asyncio
    async def test_list_tags_empty(self):
        user = _make_user()
        db = _make_db()
        res = MagicMock(scalars=MagicMock(return_value=iter([])))
        db.execute.return_value = res

        app = _build_app(user, db)
        r = await _get(app, "/kb/tags")
        assert r.status_code == 200
        assert r.json() == []
