"""Unit-тесты: favicon-прокси для закладок (GET /api/v1/bookmarks/favicon).

Покрытие:
- _favicon_cache_key: формат ключа, регистронезависимость
- Cache hit success: изображение возвращается из Redis, httpx не вызывается
- Cache hit failure (negative cache): возвращается 404 без httpx-вызова
- Cache miss + 200: изображение загружается, записывается в Redis
- Cache miss + non-200: 404, запись failure в Redis
- Cache miss + httpx.RequestError: 404, запись failure в Redis
- Cache miss + favicon too large: 404, запись failure в Redis
- Cache miss + неизвестный Content-Type: нормализация до image/x-icon
- Невалидный URL: 400
- Не-http/https схема: 400
"""

from __future__ import annotations

import base64
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

pytestmark = pytest.mark.asyncio

_FETCH_PATCH = "app.api.bookmarks._do_favicon_fetch"


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_user(role: str = "reader") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def _make_redis(cached_value: str | None = None) -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=cached_value)
    redis.setex = AsyncMock()
    return redis


def _build_app(user: SimpleNamespace, redis: AsyncMock):
    """Строит изолированный FastAPI-app с замоканными зависимостями.

    Роутер подключается без дополнительного префикса — router уже имеет
    prefix="/bookmarks", маршруты: /bookmarks/favicon, /bookmarks, etc.
    """
    from fastapi import FastAPI
    from app.api.bookmarks import router
    from app.api.deps import get_current_user, get_redis

    _app = FastAPI()
    _app.include_router(router)

    async def _fake_user():
        return user

    async def _fake_redis():
        return redis

    _app.dependency_overrides[get_current_user] = _fake_user
    _app.dependency_overrides[get_redis] = _fake_redis
    return _app


async def _get(app, url: str):
    """Выполняет GET /bookmarks/favicon?url=<url> через ASGITransport."""
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get("/bookmarks/favicon", params={"url": url})


# ── _favicon_cache_key ────────────────────────────────────────────────────────


class TestFaviconCacheKey:
    def test_returns_prefixed_key(self):
        from app.api.bookmarks import _favicon_cache_key

        key = _favicon_cache_key("https://example.com")
        assert key.startswith("favicon:v1:")
        assert len(key) > len("favicon:v1:")

    def test_same_origin_same_key(self):
        from app.api.bookmarks import _favicon_cache_key

        assert _favicon_cache_key("https://example.com") == _favicon_cache_key(
            "https://example.com"
        )

    def test_different_origins_different_keys(self):
        from app.api.bookmarks import _favicon_cache_key

        assert _favicon_cache_key("https://example.com") != _favicon_cache_key(
            "https://other.com"
        )

    def test_case_insensitive(self):
        from app.api.bookmarks import _favicon_cache_key

        assert _favicon_cache_key("HTTPS://EXAMPLE.COM") == _favicon_cache_key(
            "https://example.com"
        )

    def test_key_hex_segment_length(self):
        from app.api.bookmarks import _favicon_cache_key

        key = _favicon_cache_key("https://example.com")
        hex_part = key.split("favicon:v1:")[1]
        assert len(hex_part) == 32


# ── Cache hit (success) ───────────────────────────────────────────────────────


class TestFaviconCacheHitSuccess:
    async def test_returns_image_without_fetch(self):
        img_bytes = b"\x00\x00\x01\x00"
        cached = json.dumps(
            {"ok": True, "ct": "image/x-icon", "b64": base64.b64encode(img_bytes).decode()}
        )
        redis = _make_redis(cached)
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH) as patched:
            resp = await _get(app, "https://example.com")

        assert resp.status_code == 200
        assert resp.content == img_bytes
        patched.assert_not_called()

    async def test_returns_correct_content_type(self):
        img_bytes = b"PNG_DATA"
        cached = json.dumps(
            {"ok": True, "ct": "image/png", "b64": base64.b64encode(img_bytes).decode()}
        )
        redis = _make_redis(cached)
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH):
            resp = await _get(app, "https://example.com")

        assert resp.status_code == 200
        assert "image/png" in resp.headers["content-type"]

    async def test_does_not_write_to_redis_on_hit(self):
        img_bytes = b"\xff\xd8\xff"
        cached = json.dumps(
            {"ok": True, "ct": "image/jpeg", "b64": base64.b64encode(img_bytes).decode()}
        )
        redis = _make_redis(cached)
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH):
            await _get(app, "https://example.com")

        redis.setex.assert_not_called()


# ── Cache hit (negative / failure) ───────────────────────────────────────────


class TestFaviconCacheHitFailure:
    async def test_returns_404_from_negative_cache(self):
        redis = _make_redis(json.dumps({"ok": False}))
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH) as patched:
            resp = await _get(app, "https://unreachable.example.com")

        assert resp.status_code == 404
        patched.assert_not_called()

    async def test_does_not_write_to_redis_on_negative_hit(self):
        redis = _make_redis(json.dumps({"ok": False}))
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH):
            await _get(app, "https://unreachable.example.com")

        redis.setex.assert_not_called()


# ── Cache miss + fetch success ────────────────────────────────────────────────


class TestFaviconFetchSuccess:
    async def test_fetches_and_returns_icon(self):
        img_bytes = b"\x00\x00\x01\x00"
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH, new=AsyncMock(return_value=(200, img_bytes, "image/x-icon"))):
            resp = await _get(app, "https://example.com")

        assert resp.status_code == 200
        assert resp.content == img_bytes

    async def test_fetches_favicon_from_origin_only(self):
        img_bytes = b"DATA"
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)
        mock_fetch = AsyncMock(return_value=(200, img_bytes, "image/x-icon"))

        with patch(_FETCH_PATCH, new=mock_fetch):
            await _get(app, "https://example.com/some/deep/path?query=1")

        fetched_url = mock_fetch.call_args[0][0]
        assert fetched_url == "https://example.com/favicon.ico"

    async def test_stores_in_redis_on_success(self):
        img_bytes = b"ICON"
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH, new=AsyncMock(return_value=(200, img_bytes, "image/x-icon"))):
            await _get(app, "https://example.com")

        from app.api.bookmarks import _FAVICON_CACHE_TTL_SUCCESS

        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert args[1] == _FAVICON_CACHE_TTL_SUCCESS
        stored = json.loads(args[2])
        assert stored["ok"] is True
        assert base64.b64decode(stored["b64"]) == img_bytes

    async def test_returns_correct_content_type(self):
        img_bytes = b"DATA"
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH, new=AsyncMock(return_value=(200, img_bytes, "image/png"))):
            resp = await _get(app, "https://example.com")

        assert resp.status_code == 200
        assert "image/png" in resp.headers["content-type"]


# ── _do_favicon_fetch content-type normalisation (unit, no HTTP) ──────────────


class TestDoFaviconFetch:
    async def test_normalizes_unknown_content_type(self):
        """Неизвестный Content-Type нормализуется до image/x-icon в _do_favicon_fetch."""
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"DATA"
        mock_resp.headers = {"content-type": "application/octet-stream"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.api.bookmarks.httpx.AsyncClient", return_value=mock_client):
            from app.api.bookmarks import _do_favicon_fetch

            _, _, ct = await _do_favicon_fetch("https://example.com/favicon.ico")

        assert ct == "image/x-icon"

    async def test_strips_charset_from_content_type(self):
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"DATA"
        mock_resp.headers = {"content-type": "image/png; charset=utf-8"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.api.bookmarks.httpx.AsyncClient", return_value=mock_client):
            from app.api.bookmarks import _do_favicon_fetch

            _, _, ct = await _do_favicon_fetch("https://example.com/favicon.ico")

        assert ct == "image/png"
        assert "charset" not in ct


# ── Cache miss + fetch failure ────────────────────────────────────────────────


class TestFaviconFetchFailure:
    async def test_non_200_returns_404(self):
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH, new=AsyncMock(return_value=(404, b"", "image/x-icon"))):
            resp = await _get(app, "https://example.com")

        assert resp.status_code == 404

    async def test_non_200_stores_failure_in_redis(self):
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH, new=AsyncMock(return_value=(403, b"", "image/x-icon"))):
            await _get(app, "https://example.com")

        from app.api.bookmarks import _FAVICON_CACHE_TTL_FAILURE

        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert args[1] == _FAVICON_CACHE_TTL_FAILURE
        assert json.loads(args[2]) == {"ok": False}

    async def test_request_error_returns_404(self):
        import httpx as _httpx

        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(
            _FETCH_PATCH,
            new=AsyncMock(
                side_effect=_httpx.RequestError("Connection refused", request=None)
            ),
        ):
            resp = await _get(app, "https://unreachable.example.com")

        assert resp.status_code == 404

    async def test_request_error_stores_failure_in_redis(self):
        import httpx as _httpx

        from app.api.bookmarks import _FAVICON_CACHE_TTL_FAILURE

        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(
            _FETCH_PATCH,
            new=AsyncMock(
                side_effect=_httpx.RequestError("Timeout", request=None)
            ),
        ):
            await _get(app, "https://unreachable.example.com")

        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert args[1] == _FAVICON_CACHE_TTL_FAILURE

    async def test_oversized_favicon_returns_404(self):
        from app.api.bookmarks import _FAVICON_MAX_SIZE_BYTES

        big_content = b"X" * (_FAVICON_MAX_SIZE_BYTES + 1)
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(
            _FETCH_PATCH, new=AsyncMock(return_value=(200, big_content, "image/x-icon"))
        ):
            resp = await _get(app, "https://example.com")

        assert resp.status_code == 404

    async def test_oversized_favicon_stores_failure_in_redis(self):
        from app.api.bookmarks import _FAVICON_MAX_SIZE_BYTES, _FAVICON_CACHE_TTL_FAILURE

        big_content = b"X" * (_FAVICON_MAX_SIZE_BYTES + 1)
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(
            _FETCH_PATCH, new=AsyncMock(return_value=(200, big_content, "image/x-icon"))
        ):
            await _get(app, "https://example.com")

        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert args[1] == _FAVICON_CACHE_TTL_FAILURE


# ── URL validation ────────────────────────────────────────────────────────────


class TestFaviconUrlValidation:
    async def test_invalid_url_returns_400(self):
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/bookmarks/favicon", params={"url": "not a url at all"})

        assert resp.status_code == 400

    async def test_ftp_scheme_returns_400(self):
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        resp = await _get(app, "ftp://files.example.com/favicon.ico")

        assert resp.status_code == 400

    async def test_file_scheme_returns_400(self):
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        resp = await _get(app, "file:///etc/passwd")

        assert resp.status_code == 400

    async def test_http_url_allowed(self):
        img_bytes = b"ICON"
        redis = _make_redis(None)
        app = _build_app(_make_user(), redis)

        with patch(_FETCH_PATCH, new=AsyncMock(return_value=(200, img_bytes, "image/x-icon"))):
            resp = await _get(app, "http://intranet.company.local/page")

        assert resp.status_code == 200
