"""Unit-тесты api/bookmarks.py (Phase 4.15).

Покрытие:
- _favicon_cache_key: детерминированность и формат ключа
- _do_favicon_fetch: (через mocking) успешный запрос
- GET /bookmarks/favicon: из кэша ok / из кэша error → 404 / невалидный URL / non-http scheme /
  httpx.RequestError → 404 (кэш negative) / http_status != 200 → 404 / слишком большой контент /
  success → кэш + ответ / кэш повреждён → повторный запрос
- GET /bookmarks: возвращает список / пустой список
- POST /bookmarks: 201 created / лимит превышен 422
- DELETE /bookmarks/{id}: 204 / 404
- PATCH /bookmarks/reorder: пустой → 204 / forbidden ids / success
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role="reader",
        email="user@test.local",
    )


def _make_bookmark(
    *,
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    title: str = "Bookmark",
    url: str = "https://example.com",
    sort_order: int = 1,
) -> MagicMock:
    b = MagicMock()
    b.id = id or uuid.uuid4()
    b.user_id = user_id or uuid.uuid4()
    b.title = title
    b.url = url
    b.sort_order = sort_order
    b.resource_type = None
    b.resource_id = None
    b.group_name = None
    b.created_at = datetime.now(UTC)
    b.updated_at = datetime.now(UTC)
    return b


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.expunge = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    return AsyncMock()


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.bookmarks import router
    from app.api.deps import get_current_user, get_db, get_redis

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


async def _delete(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.delete(url)


async def _patch(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.patch(url, json=json)


# ── _favicon_cache_key ────────────────────────────────────────────────────────


class TestFaviconCacheKey:
    def test_deterministic(self):
        from app.api.bookmarks import _favicon_cache_key

        k1 = _favicon_cache_key("https://example.com")
        k2 = _favicon_cache_key("https://example.com")
        assert k1 == k2

    def test_starts_with_prefix(self):
        from app.api.bookmarks import _favicon_cache_key

        k = _favicon_cache_key("https://example.com")
        assert k.startswith("favicon:v1:")

    def test_different_origins_produce_different_keys(self):
        from app.api.bookmarks import _favicon_cache_key

        k1 = _favicon_cache_key("https://example.com")
        k2 = _favicon_cache_key("https://other.com")
        assert k1 != k2

    def test_case_insensitive(self):
        from app.api.bookmarks import _favicon_cache_key

        k1 = _favicon_cache_key("https://EXAMPLE.COM")
        k2 = _favicon_cache_key("https://example.com")
        assert k1 == k2


# ── GET /bookmarks/favicon ────────────────────────────────────────────────────


class TestGetBookmarkFavicon:
    @pytest.mark.asyncio
    async def test_returns_cached_favicon(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        import base64

        cached_data = json.dumps(
            {
                "ok": True,
                "ct": "image/x-icon",
                "b64": base64.b64encode(b"\x00\x00\x01\x00").decode(),
            }
        )
        redis.get.return_value = cached_data.encode()

        app = _build_app(user, db, redis)
        resp = await _get(app, "/bookmarks/favicon?url=https://example.com")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/x-icon"

    @pytest.mark.asyncio
    async def test_returns_404_for_cached_negative(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        redis.get.return_value = json.dumps({"ok": False}).encode()

        app = _build_app(user, db, redis)
        resp = await _get(app, "/bookmarks/favicon?url=https://example.com")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_url_scheme(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        redis.get.return_value = None

        app = _build_app(user, db, redis)
        resp = await _get(app, "/bookmarks/favicon?url=ftp://example.com")

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_returns_404_on_http_request_error(self):
        import httpx

        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        redis.get.return_value = None

        async def _fail(*args, **kwargs):
            raise httpx.ConnectError("Connection refused")

        with patch("app.api.bookmarks._do_favicon_fetch", new=_fail):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/bookmarks/favicon?url=https://example.com")

        assert resp.status_code == 404
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_404_when_http_status_not_200(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        redis.get.return_value = None

        async def _bad_status(*args, **kwargs):
            return (404, b"", "image/x-icon")

        with patch("app.api.bookmarks._do_favicon_fetch", new=_bad_status):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/bookmarks/favicon?url=https://example.com")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_when_favicon_too_large(self):
        from app.api.bookmarks import _FAVICON_MAX_SIZE_BYTES

        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        redis.get.return_value = None

        big_content = b"x" * (_FAVICON_MAX_SIZE_BYTES + 1)

        async def _big_favicon(*args, **kwargs):
            return (200, big_content, "image/x-icon")

        with patch("app.api.bookmarks._do_favicon_fetch", new=_big_favicon):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/bookmarks/favicon?url=https://example.com")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_fetches_and_caches_favicon_on_success(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        redis.get.return_value = None

        favicon_bytes = b"\x00\x00\x01\x00"

        async def _good_favicon(*args, **kwargs):
            return (200, favicon_bytes, "image/x-icon")

        with patch("app.api.bookmarks._do_favicon_fetch", new=_good_favicon):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/bookmarks/favicon?url=https://example.com")

        assert resp.status_code == 200
        assert resp.content == favicon_bytes
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_reprocesess_on_corrupt_cache(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        redis.get.return_value = b"not-valid-json{"

        favicon_bytes = b"\x00\x00"

        async def _good_favicon(*args, **kwargs):
            return (200, favicon_bytes, "image/x-icon")

        with patch("app.api.bookmarks._do_favicon_fetch", new=_good_favicon):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/bookmarks/favicon?url=https://example.com")

        assert resp.status_code == 200


# ── GET /bookmarks ─────────────────────────────────────────────────────────────


class TestListBookmarks:
    @pytest.mark.asyncio
    async def test_returns_bookmark_list(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        bm = _make_bookmark()

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [bm]
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        db.execute.side_effect = [items_result, count_result]

        from app.schemas.links import BookmarkPublic

        with patch(
            "app.api.bookmarks.BookmarkPublic.model_validate",
            side_effect=lambda obj: BookmarkPublic(
                id=obj.id,
                user_id=obj.user_id,
                title=obj.title,
                url=obj.url,
                sort_order=obj.sort_order,
                resource_type=obj.resource_type,
                resource_id=obj.resource_id,
                group_name=obj.group_name,
                created_at=obj.created_at,
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/bookmarks")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        db.execute.side_effect = [items_result, count_result]

        app = _build_app(user, db, redis)
        resp = await _get(app, "/bookmarks")

        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0}


# ── POST /bookmarks ────────────────────────────────────────────────────────────


class TestCreateBookmark:
    @pytest.mark.asyncio
    async def test_creates_bookmark_201(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        bm = _make_bookmark(user_id=user.id)

        lock_result = MagicMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        max_order_result = MagicMock()
        max_order_result.scalar_one.return_value = 0

        db.execute.side_effect = [lock_result, count_result, max_order_result]

        async def _fake_refresh(obj):
            obj.id = bm.id
            obj.user_id = user.id
            obj.title = "My Bookmark"
            obj.url = "https://example.com"
            obj.sort_order = 1
            obj.resource_type = None
            obj.resource_id = None
            obj.group_name = None
            obj.created_at = bm.created_at

        db.refresh.side_effect = _fake_refresh

        app = _build_app(user, db, redis)
        resp = await _post(
            app,
            "/bookmarks",
            json={"title": "My Bookmark", "url": "https://example.com"},
        )

        assert resp.status_code == 201
        assert resp.json()["title"] == "My Bookmark"

    @pytest.mark.asyncio
    async def test_returns_422_when_limit_exceeded(self):
        from app.api.bookmarks import MAX_BOOKMARKS_PER_USER

        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        lock_result = MagicMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = MAX_BOOKMARKS_PER_USER

        db.execute.side_effect = [lock_result, count_result]

        app = _build_app(user, db, redis)
        resp = await _post(
            app,
            "/bookmarks",
            json={"title": "One Too Many", "url": "https://example.com"},
        )

        assert resp.status_code == 422


# ── DELETE /bookmarks/{id} ─────────────────────────────────────────────────────


class TestDeleteBookmark:
    @pytest.mark.asyncio
    async def test_deletes_bookmark_204(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        bm = _make_bookmark()

        result = MagicMock()
        result.scalar_one_or_none.return_value = bm
        db.execute.return_value = result

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/bookmarks/{bm.id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/bookmarks/{uuid.uuid4()}")

        assert resp.status_code == 404


# ── PATCH /bookmarks/reorder ───────────────────────────────────────────────────


class TestReorderBookmarks:
    @pytest.mark.asyncio
    async def test_empty_items_returns_204(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        resp = await _patch(app, "/bookmarks/reorder", json={"items": []})

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_returns_403_for_foreign_bookmark_ids(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        own_id = uuid.uuid4()
        foreign_id = uuid.uuid4()

        user_ids_result = MagicMock()
        user_ids_result.all.return_value = [(own_id,)]
        db.execute.return_value = user_ids_result

        app = _build_app(user, db, redis)
        resp = await _patch(
            app,
            "/bookmarks/reorder",
            json={"items": [{"id": str(foreign_id), "sort_order": 1}]},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_reorders_successfully_204(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        bm_id = uuid.uuid4()

        user_ids_result = MagicMock()
        user_ids_result.all.return_value = [(bm_id,)]
        db.execute.side_effect = [user_ids_result, MagicMock()]

        app = _build_app(user, db, redis)
        resp = await _patch(
            app,
            "/bookmarks/reorder",
            json={"items": [{"id": str(bm_id), "sort_order": 5}]},
        )

        assert resp.status_code == 204
