"""
Test coverage for app/api/kb/articles.py

Coverage:
- GET /kb/articles: empty list / with articles / unknown-tag returns empty
- POST /kb/articles: 201 / invalid status 422 / section 404 / idempotency cached
- GET /kb/articles/{id}: success / 404 / 403 no perm / 403 draft + viewer perm
- PUT /kb/articles/{id}: success / 404 / 409 version conflict
- PUT /kb/articles/{id}/draft: success / 404 / 409 not draft
- DELETE /kb/articles/{id}: 204 / 404
- POST /kb/articles/{id}/restore: success / 404
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
    version: int = 1,
    deleted_at=None,
    created_by: uuid.UUID | None = None,
    updated_by: uuid.UUID | None = None,
) -> MagicMock:
    a = MagicMock()
    a.id = id or uuid.uuid4()
    a.section_id = section_id
    a.title = title
    a.body = body
    a.status = status
    a.version = version
    a.deleted_at = deleted_at
    a.created_at = datetime.now(UTC)
    a.updated_at = datetime.now(UTC)
    a.created_by = created_by
    a.updated_by = updated_by
    a.published_at = datetime.now(UTC) if status == "published" else None
    a.view_count = 0
    a.tags = []
    return a


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.expunge = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get.return_value = None
    return redis


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis, require_admin
    from app.api.kb.articles import router

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


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


async def _post(app, url: str, json: dict | None = None, headers: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, json=json, headers=headers or {})


async def _put(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.put(url, json=json)


async def _delete(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.delete(url)


async def _fake_apply_visibility(stmt, user, db):
    return stmt


# ── GET /kb/articles ──────────────────────────────────────────────────────────


class TestListArticles:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        articles_result = MagicMock()
        articles_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [count_result, articles_result]

        with patch(
            "app.api.kb.articles.apply_article_visibility",
            side_effect=_fake_apply_visibility,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/kb/articles")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_articles_list(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        article = _make_article(created_by=user.id)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        articles_result = MagicMock()
        articles_result.scalars.return_value.all.return_value = [article]
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [count_result, articles_result, users_result]

        with patch(
            "app.api.kb.articles.apply_article_visibility",
            side_effect=_fake_apply_visibility,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/kb/articles")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Article"

    @pytest.mark.asyncio
    async def test_unknown_tag_returns_empty(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        tag_result = MagicMock()
        tag_result.scalar_one_or_none.return_value = None
        db.execute.return_value = tag_result

        app = _build_app(user, db, redis)
        resp = await _get(app, "/kb/articles?tag=nonexistent")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_section_id_filter_applied(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        section_id = uuid.uuid4()
        article = _make_article(section_id=section_id)

        descendants_result = MagicMock()
        descendants_result.fetchall.return_value = [(section_id,)]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        articles_result = MagicMock()
        articles_result.scalars.return_value.all.return_value = [article]
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [descendants_result, count_result, articles_result, users_result]

        with patch(
            "app.api.kb.articles.apply_article_visibility",
            side_effect=_fake_apply_visibility,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles?section_id={section_id}")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_admin_can_use_status_filter(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        articles_result = MagicMock()
        articles_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [count_result, articles_result]

        with patch(
            "app.api.kb.articles.apply_article_visibility",
            side_effect=_fake_apply_visibility,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/kb/articles?status=draft")

        assert resp.status_code == 200


# ── POST /kb/articles ─────────────────────────────────────────────────────────


class TestCreateArticle:
    @pytest.mark.asyncio
    async def test_creates_article_201(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        article = _make_article(created_by=user.id, updated_by=user.id)

        db.refresh = AsyncMock(return_value=None)
        db.flush = AsyncMock(return_value=None)

        with (
            patch("app.api.kb.articles.KbArticle", return_value=article),
            patch("app.api.kb.articles.set_article_tags", new_callable=AsyncMock),
            patch("app.api.kb.articles._get_breadcrumbs", new_callable=AsyncMock, return_value=[]),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.kb.articles.clean_title", return_value="Article"),
            patch("app.api.kb.articles.sanitize_markdown", return_value="<p>Body</p>"),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                "/kb/articles",
                json={
                    "title": "Article",
                    "body": "<p>Body</p>",
                    "status": "published",
                },
            )

        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_invalid_status_returns_422(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        resp = await _post(
            app,
            "/kb/articles",
            json={"title": "Article", "body": "Body", "status": "archived"},
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_section_not_found_returns_404(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        section_result = MagicMock()
        section_result.scalar_one_or_none.return_value = None
        db.execute.return_value = section_result

        app = _build_app(user, db, redis)
        resp = await _post(
            app,
            "/kb/articles",
            json={
                "title": "Article",
                "body": "Body",
                "status": "published",
                "section_id": str(uuid.uuid4()),
            },
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_idempotency_cached_returns_cached(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        article_id = uuid.uuid4()
        cached_json = (
            f'{{"id":"{article_id}","title":"Article","body":"Body",'
            f'"section_id":null,"status":"published","version":1,'
            f'"view_count":0,"published_at":null,'
            f'"created_at":"2024-01-01T00:00:00Z","updated_at":"2024-01-01T00:00:00Z",'
            f'"tags":[],"breadcrumbs":[],"created_by":null,"updated_by":null,'
            f'"helpful":0,"not_helpful":0,"user_feedback":null,"user_permission":null}}'
        )
        redis.get.return_value = cached_json.encode()

        app = _build_app(user, db, redis)
        resp = await _post(
            app,
            "/kb/articles",
            json={"title": "Article", "body": "Body", "status": "published"},
            headers={"Idempotency-Key": "test-key-123"},
        )

        assert resp.status_code == 201
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_sets_idempotency_cache(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        article = _make_article(created_by=user.id, updated_by=user.id)

        db.refresh = AsyncMock(return_value=None)
        db.flush = AsyncMock(return_value=None)

        with (
            patch("app.api.kb.articles.KbArticle", return_value=article),
            patch("app.api.kb.articles.set_article_tags", new_callable=AsyncMock),
            patch("app.api.kb.articles._get_breadcrumbs", new_callable=AsyncMock, return_value=[]),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.kb.articles.clean_title", return_value="Article"),
            patch("app.api.kb.articles.sanitize_markdown", return_value="Body"),
        ):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                "/kb/articles",
                json={"title": "Article", "body": "Body", "status": "draft"},
                headers={"Idempotency-Key": "new-key"},
            )

        assert resp.status_code == 201
        redis.set.assert_called_once()


# ── GET /kb/articles/{id} ─────────────────────────────────────────────────────


class TestGetArticle:
    @pytest.mark.asyncio
    async def test_get_article_success(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, created_by=user.id, updated_by=user.id)
        db = _make_db()
        redis = _make_redis()

        fb_result = MagicMock()
        fb_result.one.return_value = MagicMock(helpful=3, not_helpful=1, user_fb=None)
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            users_result,
            fb_result,
        ]
        db.refresh = AsyncMock(return_value=None)

        with (
            patch(
                "app.api.kb.articles.resolve_article_permission",
                new_callable=AsyncMock,
                return_value="editor",
            ),
            patch("app.api.kb.articles.record_article_view", new_callable=AsyncMock),
            patch(
                "app.api.kb.articles._get_breadcrumbs",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}")

        assert resp.status_code == 200
        assert resp.json()["id"] == str(article_id)

    @pytest.mark.asyncio
    async def test_get_article_404(self):
        user = _make_user()
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/kb/articles/{article_id}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_article_403_no_perm(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id)
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        with patch(
            "app.api.kb.articles.resolve_article_permission",
            new_callable=AsyncMock,
            return_value=None,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_draft_403_for_viewer(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, status="draft")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        with patch(
            "app.api.kb.articles.resolve_article_permission",
            new_callable=AsyncMock,
            return_value="viewer",
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_published_as_viewer_ok(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, status="published")
        db = _make_db()
        redis = _make_redis()

        fb_result = MagicMock()
        fb_result.one.return_value = MagicMock(helpful=0, not_helpful=0, user_fb=None)
        users_result = MagicMock()
        users_result.scalars.return_value = iter([])

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            users_result,
            fb_result,
        ]
        db.refresh = AsyncMock(return_value=None)

        with (
            patch(
                "app.api.kb.articles.resolve_article_permission",
                new_callable=AsyncMock,
                return_value="viewer",
            ),
            patch("app.api.kb.articles.record_article_view", new_callable=AsyncMock),
            patch(
                "app.api.kb.articles._get_breadcrumbs",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}")

        assert resp.status_code == 200


# ── PUT /kb/articles/{id} ─────────────────────────────────────────────────────


class TestUpdateArticle:
    @pytest.mark.asyncio
    async def test_update_article_success(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=1, created_by=user.id)
        db = _make_db()
        redis = _make_redis()

        upd_result = MagicMock()
        upd_result.fetchone.return_value = (article_id,)
        creator_result = MagicMock()
        creator_result.scalar_one_or_none.return_value = None

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            upd_result,
            creator_result,
        ]
        db.refresh = AsyncMock(return_value=None)

        with (
            patch("app.api.kb.articles.require_article_permission", new_callable=AsyncMock),
            patch("app.api.kb.articles.set_article_tags", new_callable=AsyncMock),
            patch(
                "app.api.kb.articles._get_breadcrumbs",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
            patch("app.api.kb.articles.sanitize_markdown", return_value="updated body"),
        ):
            app = _build_app(user, db, redis)
            resp = await _put(
                app,
                f"/kb/articles/{article_id}",
                json={"title": "Updated", "body": "updated body", "version": 1},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_article_404(self):
        user = _make_user()
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with patch("app.api.kb.articles.require_article_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _put(app, f"/kb/articles/{article_id}", json={"version": 1})

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_article_409_version_conflict(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=2)
        db = _make_db()
        redis = _make_redis()

        upd_result = MagicMock()
        upd_result.fetchone.return_value = None

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            upd_result,
        ]

        with patch("app.api.kb.articles.require_article_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _put(app, f"/kb/articles/{article_id}", json={"version": 1})

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_update_invalid_status_422(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, version=1)
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        with patch("app.api.kb.articles.require_article_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _put(
                app,
                f"/kb/articles/{article_id}",
                json={"version": 1, "status": "badstatus"},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_article_clear_section(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(
            id=article_id, version=1, created_by=user.id, section_id=uuid.uuid4()
        )
        db = _make_db()
        redis = _make_redis()

        upd_result = MagicMock()
        upd_result.fetchone.return_value = (article_id,)
        creator_result = MagicMock()
        creator_result.scalar_one_or_none.return_value = None

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            upd_result,
            creator_result,
        ]
        db.refresh = AsyncMock(return_value=None)

        with (
            patch("app.api.kb.articles.require_article_permission", new_callable=AsyncMock),
            patch("app.api.kb.articles.set_article_tags", new_callable=AsyncMock),
            patch(
                "app.api.kb.articles._get_breadcrumbs",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _put(
                app,
                f"/kb/articles/{article_id}",
                json={"section_id": None, "version": 1},
            )

        assert resp.status_code == 200
        calls = db.execute.call_args_list
        assert len(calls) >= 2
        update_stmt = calls[1][0][0]
        compiled = update_stmt.compile()
        assert "section_id" in compiled.params
        assert compiled.params["section_id"] is None


# ── PUT /kb/articles/{id}/draft ───────────────────────────────────────────────


class TestSaveDraft:
    @pytest.mark.asyncio
    async def test_save_draft_success(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, status="draft", created_by=user.id)
        db = _make_db()
        redis = _make_redis()

        creator_result = MagicMock()
        creator_result.scalar_one_or_none.return_value = None

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            creator_result,
        ]
        db.refresh = AsyncMock(return_value=None)

        with (
            patch("app.api.kb.articles.require_article_permission", new_callable=AsyncMock),
            patch(
                "app.api.kb.articles._get_breadcrumbs",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.api.kb.articles.sanitize_markdown", return_value="new body"),
        ):
            app = _build_app(user, db, redis)
            resp = await _put(
                app,
                f"/kb/articles/{article_id}/draft",
                json={"title": "Draft", "body": "new body", "version": 1},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_save_draft_404(self):
        user = _make_user()
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        with patch("app.api.kb.articles.require_article_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _put(
                app, f"/kb/articles/{article_id}/draft", json={"title": "X", "version": 1}
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_save_draft_409_not_draft(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, status="published")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        with patch("app.api.kb.articles.require_article_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _put(
                app, f"/kb/articles/{article_id}/draft", json={"title": "X", "version": 1}
            )

        assert resp.status_code == 409


# ── DELETE /kb/articles/{id} ──────────────────────────────────────────────────


class TestDeleteArticle:
    @pytest.mark.asyncio
    async def test_delete_article_204(self):
        user = _make_user(role="admin")
        article_id = uuid.uuid4()
        article = _make_article(id=article_id)
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        with (
            patch("app.api.kb.articles.require_article_permission", new_callable=AsyncMock),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/kb/articles/{article_id}")

        assert resp.status_code == 204
        assert article.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_article_404(self):
        user = _make_user(role="admin")
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/kb/articles/{article_id}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_article_creator_success(self):
        user = _make_user(role="editor")
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, created_by=user.id)
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        with (
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/kb/articles/{article_id}")

        assert resp.status_code == 204
        assert article.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_article_forbidden(self):
        user = _make_user(role="editor")
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, created_by=uuid.uuid4())
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/kb/articles/{article_id}")

        assert resp.status_code == 403
        assert article.deleted_at is None


# ── POST /kb/articles/{id}/restore ───────────────────────────────────────────


class TestRestoreArticle:
    @pytest.mark.asyncio
    async def test_restore_article_success(self):
        user = _make_user(role="admin")
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, deleted_at=datetime.now(UTC))
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))
        db.refresh = AsyncMock(return_value=None)

        with patch(
            "app.api.kb.articles._get_breadcrumbs",
            new_callable=AsyncMock,
            return_value=[],
        ):
            app = _build_app(user, db, redis)
            resp = await _post(app, f"/kb/articles/{article_id}/restore")

        assert resp.status_code == 200
        assert article.deleted_at is None

    @pytest.mark.asyncio
    async def test_restore_article_404(self):
        user = _make_user(role="admin")
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _post(app, f"/kb/articles/{article_id}/restore")

        assert resp.status_code == 404
