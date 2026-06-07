"""Характеризующие тесты для HTTP-роутов корзины KB (app/api/kb/trash.py).

Фиксируют поведение эндпоинтов до/после выноса SQL в trash_repo (item 13).
Покрытие:
- GET /kb/trash/articles: пустой список / со статьями (sections/users/files)
- POST /kb/trash/articles/{id}/restore: success / 404
- POST /kb/trash/articles/{id}/purge: success / 404
- POST /kb/trash/purge-all: всё / older_than_days
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_admin() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role="admin",
        email="admin@test.local",
        full_name="Admin",
        avatar_url=None,
    )


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    return AsyncMock()


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_db, get_redis, require_admin
    from app.api.kb.trash import router

    _app = FastAPI()
    _app.include_router(router)

    async def _fake_db():
        return db

    async def _fake_redis():
        return redis

    _app.dependency_overrides[require_admin] = lambda: user
    _app.dependency_overrides[get_db] = _fake_db
    _app.dependency_overrides[get_redis] = _fake_redis
    return _app


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


async def _post(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url)


def _settings(retention: int = 0) -> SimpleNamespace:
    return SimpleNamespace(kb_trash_retention_days=retention)


class TestListTrash:
    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db()
        count_res = MagicMock()
        count_res.scalar.return_value = 0
        list_res = MagicMock()
        list_res.scalars.return_value.all.return_value = []
        db.execute.side_effect = [count_res, list_res]

        with patch("app.api.kb.trash.load_system_settings", return_value=_settings(0)):
            app = _build_app(_make_admin(), db, _make_redis())
            resp = await _get(app, "/kb/trash/articles")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["retention_days"] == 0
        assert data["purge_due_count"] == 0

    @pytest.mark.asyncio
    async def test_with_rows(self):
        db = _make_db()
        sec_id = uuid.uuid4()
        author_id = uuid.uuid4()
        art = SimpleNamespace(
            id=uuid.uuid4(),
            title="Trashed",
            section_id=sec_id,
            status="published",
            deleted_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=author_id,
            updated_by=author_id,
        )

        count_res = MagicMock()
        count_res.scalar.return_value = 1
        list_res = MagicMock()
        list_res.scalars.return_value.all.return_value = [art]
        sec_res = MagicMock()
        sec_res.all.return_value = [(sec_id, "Section A")]
        user_obj = SimpleNamespace(id=author_id, full_name="Author", avatar_url=None)
        users_res = MagicMock()
        users_res.scalars.return_value.all.return_value = [user_obj]
        files_res = MagicMock()
        files_res.all.return_value = [(art.id, 2, 1024)]

        db.execute.side_effect = [count_res, list_res, sec_res, users_res, files_res]

        with patch("app.api.kb.trash.load_system_settings", return_value=_settings(0)):
            app = _build_app(_make_admin(), db, _make_redis())
            resp = await _get(app, "/kb/trash/articles")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["title"] == "Trashed"
        assert item["section_title"] == "Section A"
        assert item["files_count"] == 2
        assert item["files_bytes"] == 1024
        assert item["created_by"]["full_name"] == "Author"

    @pytest.mark.asyncio
    async def test_purge_due_counted_when_retention_set(self):
        db = _make_db()
        count_res = MagicMock()
        count_res.scalar.return_value = 5
        due_res = MagicMock()
        due_res.scalar.return_value = 2
        list_res = MagicMock()
        list_res.scalars.return_value.all.return_value = []
        db.execute.side_effect = [count_res, due_res, list_res]

        with patch("app.api.kb.trash.load_system_settings", return_value=_settings(30)):
            app = _build_app(_make_admin(), db, _make_redis())
            resp = await _get(app, "/kb/trash/articles")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["purge_due_count"] == 2
        assert data["retention_days"] == 30


class TestRestoreTrash:
    @pytest.mark.asyncio
    async def test_success(self):
        db = _make_db()
        article_id = uuid.uuid4()
        art = SimpleNamespace(
            id=article_id, deleted_at=datetime.now(UTC), updated_by=None, tags=[]
        )
        res = MagicMock()
        res.scalar_one_or_none.return_value = art
        db.execute.return_value = res
        redis = _make_redis()

        with patch("app.api.kb.trash.invalidate_article_cache", new_callable=AsyncMock):
            app = _build_app(_make_admin(), db, redis)
            resp = await _post(app, f"/kb/trash/articles/{article_id}/restore")

        assert resp.status_code == 204
        assert art.deleted_at is None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_404_when_not_in_trash(self):
        db = _make_db()
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        db.execute.return_value = res

        app = _build_app(_make_admin(), db, _make_redis())
        resp = await _post(app, f"/kb/trash/articles/{uuid.uuid4()}/restore")

        assert resp.status_code == 404


class TestPurgeTrash:
    @pytest.mark.asyncio
    async def test_success(self):
        db = _make_db()
        article_id = uuid.uuid4()
        exists_res = MagicMock()
        exists_res.scalar_one_or_none.return_value = article_id
        db.execute.return_value = exists_res
        redis = _make_redis()

        with (
            patch("app.api.kb.trash.purge_article", new=AsyncMock(return_value=True)),
            patch("app.api.kb.trash.invalidate_article_cache", new_callable=AsyncMock),
        ):
            app = _build_app(_make_admin(), db, redis)
            resp = await _post(app, f"/kb/trash/articles/{article_id}/purge")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_404_when_not_in_trash(self):
        db = _make_db()
        exists_res = MagicMock()
        exists_res.scalar_one_or_none.return_value = None
        db.execute.return_value = exists_res

        app = _build_app(_make_admin(), db, _make_redis())
        resp = await _post(app, f"/kb/trash/articles/{uuid.uuid4()}/purge")

        assert resp.status_code == 404


class TestPurgeAll:
    @pytest.mark.asyncio
    async def test_purge_all(self):
        db = _make_db()
        redis = _make_redis()

        with patch("app.api.kb.trash._purge_all", new=AsyncMock(return_value=3)):
            app = _build_app(_make_admin(), db, redis)
            resp = await _post(app, "/kb/trash/purge-all")

        assert resp.status_code == 200
        assert resp.json()["purged"] == 3

    @pytest.mark.asyncio
    async def test_purge_older_than(self):
        db = _make_db()
        redis = _make_redis()

        with patch(
            "app.api.kb.trash.purge_expired_articles", new=AsyncMock(return_value=1)
        ) as mock_exp:
            app = _build_app(_make_admin(), db, redis)
            resp = await _post(app, "/kb/trash/purge-all?older_than_days=7")

        assert resp.status_code == 200
        assert resp.json()["purged"] == 1
        mock_exp.assert_awaited_once()
