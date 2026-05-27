"""Unit tests for KB comments, suggestions, and feedback API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("httpx", reason="httpx not installed")


def _make_user(role: str = "reader") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        full_name="Test User",
        avatar_url=None,
        email="u@test.local",
    )


def _make_article(**kw):
    a = MagicMock()
    a.id = kw.get("id", uuid.uuid4())
    a.title = kw.get("title", "Test Article")
    a.section_id = kw.get("section_id")
    a.created_by = kw.get("created_by", uuid.uuid4())
    a.status = kw.get("status", "published")
    a.inherit_permissions = kw.get("inherit_permissions", True)
    return a


def _make_comment(**kw):
    c = MagicMock()
    c.id = kw.get("id", uuid.uuid4())
    c.article_id = kw.get("article_id", uuid.uuid4())
    c.author_id = kw.get("author_id", uuid.uuid4())
    c.body = kw.get("body", "Comment text")
    c.deleted_at = kw.get("deleted_at")
    c.created_at = kw.get("created_at", datetime.now(UTC))
    c.updated_at = kw.get("updated_at", datetime.now(UTC))
    return c


def _make_suggestion(**kw):
    s = MagicMock()
    s.id = kw.get("id", uuid.uuid4())
    s.article_id = kw.get("article_id", uuid.uuid4())
    s.author_id = kw.get("author_id", uuid.uuid4())
    s.body = kw.get("body", "Suggested edit")
    s.comment = kw.get("comment")
    s.status = kw.get("status", "pending")
    s.reviewed_at = kw.get("reviewed_at")
    s.reviewed_by = kw.get("reviewed_by")
    s.created_at = kw.get("created_at", datetime.now(UTC))
    return s


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    db.refresh = MagicMock()
    db.expunge = MagicMock()
    db.add_all = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value.all.return_value = []
    result.scalar_one.return_value = 0
    db.execute.return_value = result
    return db


def _build_comments_app(user, db, redis=None):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.kb.comments import router

    app = FastAPI()
    app.include_router(router)

    if redis is None:
        redis = AsyncMock()

    async def _user():
        return user

    async def _db():
        return db

    async def _redis():
        return redis

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    return app


def _build_suggestions_app(user, db, redis=None):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.kb.suggestions import router

    app = FastAPI()
    app.include_router(router)

    if redis is None:
        redis = AsyncMock()

    async def _user():
        return user

    async def _db():
        return db

    async def _redis():
        return redis

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    return app


def _build_feedback_app(user, db, redis=None):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.kb.feedback import router

    app = FastAPI()
    app.include_router(router)

    if redis is None:
        redis = AsyncMock()

    async def _user():
        return user

    async def _db():
        return db

    async def _redis():
        return redis

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
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


async def _delete(app, url):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.delete(url)


class TestKbComments:
    @pytest.mark.asyncio
    async def test_list_comments_404_article_not_found(self):
        user = _make_user()
        db = _make_db()

        article_result = MagicMock()
        article_result.scalar_one_or_none.return_value = None
        db.execute.return_value = article_result

        app = _build_comments_app(user, db)

        with patch("app.api.kb.comments._get_article_or_404") as mock_get:
            from fastapi import HTTPException

            mock_get.side_effect = HTTPException(status_code=404, detail="Not found")
            r = await _get(app, f"/kb/articles/{uuid.uuid4()}/comments")

        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_list_comments_success_empty(self):
        user = _make_user()
        article = _make_article()
        db = _make_db()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [count_result, items_result]

        app = _build_comments_app(user, db)

        with patch("app.api.kb.comments._get_article_or_404", AsyncMock(return_value=article)), \
             patch("app.api.kb.comments.require_article_permission", AsyncMock()):
            r = await _get(app, f"/kb/articles/{article.id}/comments")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_comments_with_items(self):
        user = _make_user()
        article = _make_article()
        db = _make_db()

        comment = _make_comment(article_id=article.id, author_id=user.id)
        author_user = MagicMock()
        author_user.id = user.id
        author_user.full_name = "Test User"
        author_user.avatar_url = None

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [comment]

        users_result = MagicMock()
        users_result.scalars.return_value = iter([author_user])

        db.execute.side_effect = [count_result, items_result, users_result]

        app = _build_comments_app(user, db)

        with patch("app.api.kb.comments._get_article_or_404", AsyncMock(return_value=article)), \
             patch("app.api.kb.comments.require_article_permission", AsyncMock()):
            r = await _get(app, f"/kb/articles/{article.id}/comments")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_create_comment_success(self):
        user = _make_user()
        article = _make_article()
        db = _make_db()

        new_comment = _make_comment(article_id=article.id, author_id=user.id)
        db.refresh = AsyncMock()

        app = _build_comments_app(user, db)

        with patch("app.api.kb.comments._get_article_or_404", AsyncMock(return_value=article)), \
             patch("app.api.kb.comments.require_article_permission", AsyncMock()), \
             patch("app.api.kb.comments.KbArticleComment") as mock_cls:
            mock_cls.return_value = new_comment

            async def _fake_refresh(obj):
                pass

            db.refresh.side_effect = _fake_refresh
            r = await _post(app, f"/kb/articles/{article.id}/comments", json={"body": "Nice!"})

        assert r.status_code == 201

    @pytest.mark.asyncio
    async def test_create_comment_article_not_found(self):
        user = _make_user()
        db = _make_db()
        app = _build_comments_app(user, db)

        with patch("app.api.kb.comments._get_article_or_404") as mock_get:
            from fastapi import HTTPException

            mock_get.side_effect = HTTPException(status_code=404, detail="Not found")
            r = await _post(app, f"/kb/articles/{uuid.uuid4()}/comments", json={"body": "test"})

        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_comment_success(self):
        user = _make_user(role="admin")
        comment = _make_comment(author_id=user.id)
        db = _make_db()

        result = MagicMock()
        result.scalar_one_or_none.return_value = comment
        db.execute.return_value = result

        app = _build_comments_app(user, db)

        r = await _delete(app, f"/kb/articles/{comment.article_id}/comments/{comment.id}")

        assert r.status_code == 204
        assert comment.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_comment_not_found(self):
        user = _make_user()
        db = _make_db()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        app = _build_comments_app(user, db)

        r = await _delete(app, f"/kb/articles/{uuid.uuid4()}/comments/{uuid.uuid4()}")

        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_comment_already_deleted(self):
        user = _make_user()
        comment = _make_comment(author_id=user.id, deleted_at=datetime.now(UTC))
        db = _make_db()

        result = MagicMock()
        result.scalar_one_or_none.return_value = comment
        db.execute.return_value = result

        app = _build_comments_app(user, db)

        r = await _delete(app, f"/kb/articles/{comment.article_id}/comments/{comment.id}")

        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_comment_forbidden(self):
        user = _make_user(role="reader")
        other_user_id = uuid.uuid4()
        comment = _make_comment(author_id=other_user_id)
        db = _make_db()

        result = MagicMock()
        result.scalar_one_or_none.return_value = comment
        db.execute.return_value = result

        app = _build_comments_app(user, db)

        r = await _delete(app, f"/kb/articles/{comment.article_id}/comments/{comment.id}")

        assert r.status_code == 403


class TestKbSuggestions:
    @pytest.mark.asyncio
    async def test_suggest_edit_success(self):
        user = _make_user()
        article = _make_article()
        db = _make_db()

        suggestion = _make_suggestion(article_id=article.id, author_id=user.id)

        async def _fake_refresh(obj):
            pass

        db.refresh.side_effect = _fake_refresh

        app = _build_suggestions_app(user, db)

        with patch("app.api.kb.suggestions._get_article_or_404", AsyncMock(return_value=article)), \
             patch("app.api.kb.suggestions.require_article_permission", AsyncMock()), \
             patch("app.api.kb.suggestions.KbSuggestion") as mock_cls:
            mock_cls.return_value = suggestion
            r = await _post(
                app,
                f"/kb/articles/{article.id}/suggest",
                json={"body": "Better version", "comment": "Fix typo"},
            )

        assert r.status_code == 202
        data = r.json()
        assert "suggestion_id" in data

    @pytest.mark.asyncio
    async def test_suggest_edit_article_not_found(self):
        user = _make_user()
        db = _make_db()
        app = _build_suggestions_app(user, db)

        with patch("app.api.kb.suggestions._get_article_or_404") as mock_get:
            from fastapi import HTTPException

            mock_get.side_effect = HTTPException(status_code=404, detail="Not found")
            r = await _post(
                app, f"/kb/articles/{uuid.uuid4()}/suggest", json={"body": "x", "comment": ""}
            )

        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_list_suggestions_empty(self):
        user = _make_user(role="editor")
        article = _make_article()
        db = _make_db()

        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        app = _build_suggestions_app(user, db)

        with patch("app.api.kb.suggestions._get_article_or_404", AsyncMock(return_value=article)), \
             patch("app.api.kb.suggestions.require_article_permission", AsyncMock()):
            r = await _get(app, f"/kb/articles/{article.id}/suggestions")

        assert r.status_code == 200
        assert r.json()["items"] == []

    @pytest.mark.asyncio
    async def test_list_suggestions_with_items(self):
        user = _make_user(role="editor")
        article = _make_article()
        db = _make_db()

        suggestion = _make_suggestion(article_id=article.id, author_id=user.id)
        author_user = MagicMock()
        author_user.id = user.id
        author_user.full_name = "Test User"
        author_user.avatar_url = None

        suggestions_result = MagicMock()
        suggestions_result.scalars.return_value.all.return_value = [suggestion]

        users_result = MagicMock()
        users_result.scalars.return_value = iter([author_user])

        db.execute.side_effect = [suggestions_result, users_result]

        app = _build_suggestions_app(user, db)

        with patch("app.api.kb.suggestions._get_article_or_404", AsyncMock(return_value=article)), \
             patch("app.api.kb.suggestions.require_article_permission", AsyncMock()):
            r = await _get(app, f"/kb/articles/{article.id}/suggestions")

        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_review_suggestion_approve(self):
        user = _make_user(role="editor")
        article = _make_article()
        suggestion = _make_suggestion(article_id=article.id)
        db = _make_db()

        sugg_result = MagicMock()
        sugg_result.scalar_one_or_none.return_value = suggestion

        article_result = MagicMock()
        article_result.scalar_one_or_none.return_value = article

        db.execute.side_effect = [sugg_result, article_result]

        app = _build_suggestions_app(user, db)

        with patch("app.api.kb.suggestions.require_article_permission", AsyncMock()), \
             patch("app.api.kb.suggestions.notify_suggestion_reviewed", AsyncMock()):
            r = await _post(
                app,
                f"/kb/suggestions/{suggestion.id}/review",
                json={"action": "approve"},
            )

        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    @pytest.mark.asyncio
    async def test_review_suggestion_reject(self):
        user = _make_user(role="editor")
        article = _make_article()
        suggestion = _make_suggestion(article_id=article.id)
        db = _make_db()

        sugg_result = MagicMock()
        sugg_result.scalar_one_or_none.return_value = suggestion

        article_result = MagicMock()
        article_result.scalar_one_or_none.return_value = article

        db.execute.side_effect = [sugg_result, article_result]

        app = _build_suggestions_app(user, db)

        with patch("app.api.kb.suggestions.require_article_permission", AsyncMock()), \
             patch("app.api.kb.suggestions.notify_suggestion_reviewed", AsyncMock()):
            r = await _post(
                app,
                f"/kb/suggestions/{suggestion.id}/review",
                json={"action": "reject"},
            )

        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_review_suggestion_not_found(self):
        user = _make_user(role="editor")
        db = _make_db()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        app = _build_suggestions_app(user, db)

        r = await _post(
            app,
            f"/kb/suggestions/{uuid.uuid4()}/review",
            json={"action": "approve"},
        )

        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_review_suggestion_already_reviewed_409(self):
        user = _make_user(role="editor")
        suggestion = _make_suggestion(status="approved")
        db = _make_db()

        result = MagicMock()
        result.scalar_one_or_none.return_value = suggestion
        db.execute.return_value = result

        app = _build_suggestions_app(user, db)

        r = await _post(
            app,
            f"/kb/suggestions/{suggestion.id}/review",
            json={"action": "approve"},
        )

        assert r.status_code == 409


class TestKbFeedback:
    @pytest.mark.asyncio
    async def test_submit_feedback_new(self):
        user = _make_user()
        article = _make_article()
        db = _make_db()

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None

        helpful_result = MagicMock()
        helpful_result.scalar_one.return_value = 1

        not_helpful_result = MagicMock()
        not_helpful_result.scalar_one.return_value = 0

        db.execute.side_effect = [existing_result, helpful_result, not_helpful_result]

        app = _build_feedback_app(user, db)

        with patch("app.api.kb.feedback._get_article_or_404", AsyncMock(return_value=article)), \
             patch("app.api.kb.feedback.require_article_permission", AsyncMock()):
            r = await _post(app, f"/kb/articles/{article.id}/feedback", json={"is_helpful": True})

        assert r.status_code == 200
        data = r.json()
        assert data["helpful_count"] == 1
        assert data["not_helpful_count"] == 0
        assert data["user_feedback"] is True

    @pytest.mark.asyncio
    async def test_submit_feedback_update_existing(self):
        user = _make_user()
        article = _make_article()
        db = _make_db()

        existing_fb = MagicMock()
        existing_fb.is_helpful = True

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_fb

        helpful_result = MagicMock()
        helpful_result.scalar_one.return_value = 0

        not_helpful_result = MagicMock()
        not_helpful_result.scalar_one.return_value = 1

        db.execute.side_effect = [existing_result, helpful_result, not_helpful_result]

        app = _build_feedback_app(user, db)

        with patch("app.api.kb.feedback._get_article_or_404", AsyncMock(return_value=article)), \
             patch("app.api.kb.feedback.require_article_permission", AsyncMock()):
            r = await _post(app, f"/kb/articles/{article.id}/feedback", json={"is_helpful": False})

        assert r.status_code == 200
        assert existing_fb.is_helpful is False

    @pytest.mark.asyncio
    async def test_submit_feedback_article_not_found(self):
        user = _make_user()
        db = _make_db()
        app = _build_feedback_app(user, db)

        with patch("app.api.kb.feedback._get_article_or_404") as mock_get:
            from fastapi import HTTPException

            mock_get.side_effect = HTTPException(status_code=404, detail="Not found")
            r = await _post(app, f"/kb/articles/{uuid.uuid4()}/feedback", json={"is_helpful": True})

        assert r.status_code == 404
