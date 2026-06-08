"""News comments — route-level unit tests (db mocked, ASGI transport).

Mirror of ``test_kb_comments_suggestions.py`` for the news comments router.
Covers: list (empty / with items), create (+counter), edit (author / foreign /
deleted), delete (own soft + counter / admin / foreign / already-deleted).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("httpx", reason="httpx not installed")

_MOD = "app.api.news.comments"


def _make_user(role: str = "reader") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        full_name="Test User",
        department="IT",
        avatar_url=None,
        email="u@test.local",
    )


def _make_news(**kw):
    n = MagicMock()
    n.id = kw.get("id", uuid.uuid4())
    n.status = kw.get("status", "published")
    return n


def _make_comment(**kw):
    c = MagicMock()
    c.id = kw.get("id", uuid.uuid4())
    c.news_id = kw.get("news_id", uuid.uuid4())
    c.author_id = kw.get("author_id", uuid.uuid4())
    c.body = kw.get("body", "Comment text")
    c.deleted_at = kw.get("deleted_at")
    c.created_at = kw.get("created_at", datetime.now(UTC))
    c.updated_at = kw.get("updated_at", datetime.now(UTC))
    return c


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _build_app(user, db):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db
    from app.api.news.comments import router

    app = FastAPI()
    app.include_router(router, prefix="/news")

    async def _user():
        return user

    async def _db():
        return db

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    return app


async def _request(app, method, url, **kw):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.request(method, url, **kw)


class TestListComments:
    @pytest.mark.asyncio
    async def test_empty(self):
        user = _make_user()
        news = _make_news()
        db = _make_db()
        app = _build_app(user, db)

        with (
            patch(f"{_MOD}._get_news_or_404", AsyncMock(return_value=news)),
            patch(f"{_MOD}.require_news_read_access"),
            patch(f"{_MOD}.comments_repo.count_active_comments", AsyncMock(return_value=0)),
            patch(f"{_MOD}.comments_repo.list_comments", AsyncMock(return_value=[])),
            patch(f"{_MOD}.comments_repo.get_comment_authors", AsyncMock(return_value={})),
        ):
            r = await _request(app, "GET", f"/news/{news.id}/comments")

        assert r.status_code == 200
        data = r.json()
        assert data == {"items": [], "total": 0}

    @pytest.mark.asyncio
    async def test_with_items_and_deleted(self):
        user = _make_user()
        news = _make_news()
        db = _make_db()
        active = _make_comment(news_id=news.id, author_id=user.id)
        gone = _make_comment(news_id=news.id, author_id=None, deleted_at=datetime.now(UTC))
        app = _build_app(user, db)

        with (
            patch(f"{_MOD}._get_news_or_404", AsyncMock(return_value=news)),
            patch(f"{_MOD}.require_news_read_access"),
            patch(f"{_MOD}.comments_repo.count_active_comments", AsyncMock(return_value=1)),
            patch(
                f"{_MOD}.comments_repo.list_comments",
                AsyncMock(return_value=[active, gone]),
            ),
            patch(
                f"{_MOD}.comments_repo.get_comment_authors",
                AsyncMock(return_value={user.id: user}),
            ),
        ):
            r = await _request(app, "GET", f"/news/{news.id}/comments")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        items = data["items"]
        assert items[0]["body"] == "Comment text"
        assert items[0]["author"]["full_name"] == "Test User"
        assert items[1]["is_deleted"] is True
        assert items[1]["body"] is None
        assert items[1]["author"] is None


class TestCreateComment:
    @pytest.mark.asyncio
    async def test_increments_counter(self):
        user = _make_user()
        news = _make_news()
        db = _make_db()
        created = _make_comment(news_id=news.id, author_id=user.id)
        inc = AsyncMock()
        app = _build_app(user, db)

        with (
            patch(f"{_MOD}._get_news_or_404", AsyncMock(return_value=news)),
            patch(f"{_MOD}.require_news_read_access"),
            patch(f"{_MOD}.sanitize_markdown", side_effect=lambda b: b),
            patch(f"{_MOD}.NewsComment", return_value=created),
            patch(f"{_MOD}.comments_repo.increment_comment_count", inc),
        ):
            r = await _request(
                app, "POST", f"/news/{news.id}/comments", json={"body": "Nice!"}
            )

        assert r.status_code == 201
        data = r.json()
        assert data["author"]["full_name"] == "Test User"
        inc.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_body_422(self):
        user = _make_user()
        news = _make_news()
        db = _make_db()
        app = _build_app(user, db)

        with (
            patch(f"{_MOD}._get_news_or_404", AsyncMock(return_value=news)),
            patch(f"{_MOD}.require_news_read_access"),
        ):
            r = await _request(app, "POST", f"/news/{news.id}/comments", json={"body": ""})

        assert r.status_code == 422


class TestUpdateComment:
    @pytest.mark.asyncio
    async def test_author_can_edit(self):
        user = _make_user()
        comment = _make_comment(author_id=user.id)
        db = _make_db()
        app = _build_app(user, db)

        with (
            patch(f"{_MOD}.comments_repo.get_comment", AsyncMock(return_value=comment)),
            patch(f"{_MOD}.sanitize_markdown", side_effect=lambda b: b),
        ):
            r = await _request(
                app,
                "PATCH",
                f"/news/{comment.news_id}/comments/{comment.id}",
                json={"body": "edited"},
            )

        assert r.status_code == 200
        assert comment.body == "edited"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_foreign_edit_forbidden(self):
        user = _make_user()
        comment = _make_comment(author_id=uuid.uuid4())
        db = _make_db()
        app = _build_app(user, db)

        with patch(f"{_MOD}.comments_repo.get_comment", AsyncMock(return_value=comment)):
            r = await _request(
                app,
                "PATCH",
                f"/news/{comment.news_id}/comments/{comment.id}",
                json={"body": "edited"},
            )

        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_deleted_conflict(self):
        user = _make_user()
        comment = _make_comment(author_id=user.id, deleted_at=datetime.now(UTC))
        db = _make_db()
        app = _build_app(user, db)

        with patch(f"{_MOD}.comments_repo.get_comment", AsyncMock(return_value=comment)):
            r = await _request(
                app,
                "PATCH",
                f"/news/{comment.news_id}/comments/{comment.id}",
                json={"body": "edited"},
            )

        assert r.status_code == 409


class TestDeleteComment:
    @pytest.mark.asyncio
    async def test_author_soft_delete_decrements(self):
        user = _make_user()
        comment = _make_comment(author_id=user.id)
        db = _make_db()
        dec = AsyncMock()
        app = _build_app(user, db)

        with (
            patch(f"{_MOD}.comments_repo.get_comment", AsyncMock(return_value=comment)),
            patch(f"{_MOD}.comments_repo.decrement_comment_count", dec),
        ):
            r = await _request(
                app, "DELETE", f"/news/{comment.news_id}/comments/{comment.id}"
            )

        assert r.status_code == 204
        assert comment.deleted_at is not None
        dec.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_admin_can_delete_foreign(self):
        admin = _make_user(role="admin")
        comment = _make_comment(author_id=uuid.uuid4())
        db = _make_db()
        app = _build_app(admin, db)

        with (
            patch(f"{_MOD}.comments_repo.get_comment", AsyncMock(return_value=comment)),
            patch(f"{_MOD}.comments_repo.decrement_comment_count", AsyncMock()),
        ):
            r = await _request(
                app, "DELETE", f"/news/{comment.news_id}/comments/{comment.id}"
            )

        assert r.status_code == 204

    @pytest.mark.asyncio
    async def test_foreign_delete_forbidden(self):
        user = _make_user()
        comment = _make_comment(author_id=uuid.uuid4())
        db = _make_db()
        app = _build_app(user, db)

        with patch(f"{_MOD}.comments_repo.get_comment", AsyncMock(return_value=comment)):
            r = await _request(
                app, "DELETE", f"/news/{comment.news_id}/comments/{comment.id}"
            )

        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_already_deleted_conflict(self):
        user = _make_user()
        comment = _make_comment(author_id=user.id, deleted_at=datetime.now(UTC))
        db = _make_db()
        app = _build_app(user, db)

        with patch(f"{_MOD}.comments_repo.get_comment", AsyncMock(return_value=comment)):
            r = await _request(
                app, "DELETE", f"/news/{comment.news_id}/comments/{comment.id}"
            )

        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_not_found(self):
        user = _make_user()
        db = _make_db()
        app = _build_app(user, db)

        with patch(f"{_MOD}.comments_repo.get_comment", AsyncMock(return_value=None)):
            r = await _request(
                app, "DELETE", f"/news/{uuid.uuid4()}/comments/{uuid.uuid4()}"
            )

        assert r.status_code == 404
