"""Unit-тесты для app/api/kb/versions.py.

Покрытие:
- GET /kb/articles/{id}/versions: success / 404 article / нет прав / с пагинацией
- POST /kb/articles/{id}/versions/{n}/restore: success / 404 article / версия не найдена / нет прав
- GET /kb/articles/{id}/versions/{v1}/diff/{v2}: success / 404 article / версия не найдена / нет diff
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_user(role: str = "editor") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        email=f"{role}@test.local",
        full_name="Test User",
        avatar_url=None,
    )


def _make_article(
    *,
    id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
    title: str = "Article",
    body: str = "<p>Body</p>",
    status: str = "published",
    version: int = 3,
    deleted_at=None,
) -> MagicMock:
    a = MagicMock()
    a.id = id or uuid.uuid4()
    a.section_id = section_id or uuid.uuid4()
    a.title = title
    a.body = body
    a.status = status
    a.version = version
    a.deleted_at = deleted_at
    a.created_at = datetime.now(UTC)
    a.updated_at = datetime.now(UTC)
    a.created_by = None
    a.updated_by = None
    a.published_at = None
    a.view_count = 0
    a.tags = []
    return a


def _make_version(
    *,
    id: uuid.UUID | None = None,
    article_id: uuid.UUID | None = None,
    version: int = 1,
    title: str = "Old Title",
    body: str = "<p>Old</p>",
    change_comment: str = "initial",
    changed_by: uuid.UUID | None = None,
) -> MagicMock:
    v = MagicMock()
    v.id = id or uuid.uuid4()
    v.article_id = article_id or uuid.uuid4()
    v.version = version
    v.title = title
    v.body = body
    v.change_comment = change_comment
    v.changed_by = changed_by
    v.created_at = datetime.now(UTC)
    return v


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    return AsyncMock()


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.kb.versions import router

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
    return _app


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


async def _post(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, json=json)


# ── GET /kb/articles/{id}/versions ───────────────────────────────────────────


class TestListVersions:
    @pytest.mark.asyncio
    async def test_returns_versions_list(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id)
        ver1 = _make_version(article_id=article_id, version=1)
        ver2 = _make_version(article_id=article_id, version=2)

        db = _make_db()
        redis = _make_redis()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        versions_result = MagicMock()
        versions_result.scalars.return_value.all.return_value = [ver2, ver1]
        users_result = MagicMock()
        users_result.scalars.return_value = iter([])

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            count_result,
            versions_result,
            users_result,
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_404_when_article_not_found(self):
        user = _make_user()
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        )

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_versions_list(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id)
        db = _make_db()
        redis = _make_redis()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        versions_result = MagicMock()
        versions_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            count_result,
            versions_result,
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_versions_with_changed_by_user(self):
        user = _make_user()
        changer_id = uuid.uuid4()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id)
        ver = _make_version(article_id=article_id, version=1, changed_by=changer_id)

        changer = MagicMock()
        changer.id = changer_id
        changer.full_name = "Changer"
        changer.avatar_url = None

        db = _make_db()
        redis = _make_redis()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        versions_result = MagicMock()
        versions_result.scalars.return_value.all.return_value = [ver]
        users_result = MagicMock()
        users_result.scalars.return_value = iter([changer])

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            count_result,
            versions_result,
            users_result,
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["changed_by"]["full_name"] == "Changer"


# ── POST /kb/articles/{id}/versions/{n}/restore ───────────────────────────────


class TestRestoreVersion:
    @pytest.mark.asyncio
    async def test_restores_version_successfully(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=3, title="Current", body="<p>New</p>")
        snap = _make_version(article_id=article_id, version=1, title="Old", body="<p>Old</p>")

        db = _make_db()
        redis = _make_redis()

        breadcrumbs_result = MagicMock()
        breadcrumbs_result.fetchall.return_value = []

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=snap)),
            breadcrumbs_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _post(app, f"/kb/articles/{article_id}/versions/1/restore")

        assert resp.status_code == 200
        db.add.assert_called()
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_404_when_article_not_found(self):
        user = _make_user()
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        )

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _post(app, f"/kb/articles/{article_id}/versions/1/restore")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_404_when_version_not_found(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=5)
        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _post(app, f"/kb/articles/{article_id}/versions/99/restore")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_restore_to_current_version(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=3)
        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _post(app, f"/kb/articles/{article_id}/versions/3/restore")

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cannot restore to the current active version"

    @pytest.mark.asyncio
    async def test_restores_empty_body_correctly(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=3, title="Current", body="<p>New</p>")
        snap = _make_version(article_id=article_id, version=1, title="Old", body="")

        db = _make_db()
        redis = _make_redis()

        breadcrumbs_result = MagicMock()
        breadcrumbs_result.fetchall.return_value = []

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=snap)),
            breadcrumbs_result,
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _post(app, f"/kb/articles/{article_id}/versions/1/restore")

        assert resp.status_code == 200
        assert article.body == ""


# ── GET /kb/articles/{id}/versions/{v1}/diff/{v2} ─────────────────────────────


class TestDiffVersions:
    @pytest.mark.asyncio
    async def test_returns_diff_hunks(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=3, body="line1\nline2\n")
        ver1 = _make_version(article_id=article_id, version=1, body="line1\n")
        ver2 = _make_version(article_id=article_id, version=2, body="line1\nline2\n")

        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=ver1)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=ver2)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions/1/diff/2")

        assert resp.status_code == 200
        data = resp.json()
        assert "hunks" in data
        assert "stats" in data

    @pytest.mark.asyncio
    async def test_404_when_article_not_found(self):
        user = _make_user()
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        )

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions/1/diff/2")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_404_when_version_not_found_in_diff(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=5, body="current\n")

        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions/99/diff/100")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_against_current_version(self):
        """v2 == article.version => uses article.body directly."""
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=3, body="current body\n")
        ver1 = _make_version(article_id=article_id, version=1, body="old body\n")

        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=ver1)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions/1/diff/3")

        assert resp.status_code == 200
        data = resp.json()
        assert "hunks" in data
        assert data["stats"]["added"] >= 0

    @pytest.mark.asyncio
    async def test_identical_versions_return_empty_diff(self):
        user = _make_user()
        article_id = uuid.uuid4()
        same_body = "identical content\n"
        article = _make_article(id=article_id, version=5, body=same_body)
        ver1 = _make_version(article_id=article_id, version=1, body=same_body)
        ver2 = _make_version(article_id=article_id, version=2, body=same_body)

        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=ver1)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=ver2)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions/1/diff/2")

        assert resp.status_code == 200
        data = resp.json()
        assert data["hunks"] == []
        assert data["stats"]["added"] == 0
        assert data["stats"]["removed"] == 0

    @pytest.mark.asyncio
    async def test_diff_too_large_returns_413(self):
        user = _make_user()
        article_id = uuid.uuid4()
        large_body = "x" * 500_001
        article = _make_article(id=article_id, version=5, body=large_body)
        ver1 = _make_version(article_id=article_id, version=1, body=large_body)

        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=ver1)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions/1/diff/5")

        assert resp.status_code == 413


# ── GET /kb/articles/{id}/versions/{version_number} ─────────────────────────


class TestGetVersion:
    @pytest.mark.asyncio
    async def test_get_version_success(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id)
        ver = _make_version(article_id=article_id, version=1, body="Version 1 Body")

        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=ver)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 1
        assert data["body"] == "Version 1 Body"

    @pytest.mark.asyncio
    async def test_get_version_not_found(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id)

        db = _make_db()
        redis = _make_redis()

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        with patch(
            "app.api.kb.versions.require_article_permission", new_callable=AsyncMock
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/versions/100")

        assert resp.status_code == 404
