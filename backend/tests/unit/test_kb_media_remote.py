"""Unit-тесты: re-host внешних картинок в KB (POST /api/v1/kb/articles/{id}/media/remote).

Покрытие:
- _derive_remote_filename: имя из URL, fallback по Content-Type, санитизация
- save_bytes_to_path: размер/MIME-валидация, запись
- SSRF-блок приватных/loopback/cloud-metadata IP → 422 без fetch
- Redirect на private → 422 без второго запроса
- DNS-rebinding → 422 без соединения
- Не-картинка по Content-Type → 422
- Превышение размера (Content-Length и бегущий счётчик) → 413
- Happy-path: валидные PNG-bytes → 201, URL возвращён, файл записан
- Права: не-editor → 403
- Невалидный URL/схема → 422 (pydantic-валидация)
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

# Сохраняем реальный AsyncClient ДО любых патчей httpx: production-код
# (app.api.kb.media._fetch_remote_image) использует httpx.AsyncClient, и мы
# патчим его в fetch-тестах. Без этого ASGI-транспорт тестового клиента тоже
# сломался бы.
_REAL_ASYNC_CLIENT = httpx.AsyncClient

# Патчи для мокирования сети/SSRF (как в test_bookmarks_favicon.py).
_FETCH_PATCH = "app.api.kb.media._fetch_remote_image"
_SSRF_PATCH = "app.api.kb.media.assert_url_safe"
_RESOLVE_PATCH = "app.api.kb.media.resolve_stable_ip"


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_user(role: str = "reader") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role=role, full_name="Tester")


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    return redis


def _build_app(user: SimpleNamespace, redis: AsyncMock, *, kb_media_dir: Path):
    """Изолированный FastAPI-app с замоканными зависимостями.

    ``KB_MEDIA_DIR`` — module-level Path; патчим на временный каталог, чтобы
    happy-path реально записывал файл в изолированное место.
    """
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_redis
    from app.api.kb.media import router

    _app = FastAPI()
    _app.include_router(router)

    async def _fake_user():
        return user

    async def _fake_redis():
        return redis

    _app.dependency_overrides[get_current_user] = _fake_user
    _app.dependency_overrides[get_redis] = _fake_redis
    _app.state._kb_media_dir = kb_media_dir
    return _app


async def _post_remote(app, article_id: uuid.UUID, url: str):
    """POST /kb/articles/{id}/media/remote через ASGITransport.

    Использует сохранённый реальный ``_REAL_ASYNC_CLIENT`` — fetch-тесты патчат
    глобальный ``httpx.AsyncClient`` (который дёргает production-код), и без
    этого пина тестовый ASGI-клиент тоже сломался бы.
    """
    async with _REAL_ASYNC_CLIENT(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(f"/kb/articles/{article_id}/media/remote", json={"url": url})


def _make_streaming_client(resp_mocks: list):
    """Сборка httpx.AsyncClient-mock с очередью ответов stream-контекстов.

    ``resp_mocks`` — список dict'ов вида ``{status, headers, body}``. Каждый
    ответ возвращается последовательно при ``client.stream(...)`` (эмуляция
    редиректов: 302 → следующий ответ). Используется в fetch-тестах, где
    патчим ``httpx.AsyncClient`` целиком.
    """
    queue = list(resp_mocks)

    def _build_stream_ctx(rm: dict):
        ctx = MagicMock()
        fake_resp = MagicMock()
        fake_resp.status_code = rm["status"]
        headers = dict(rm.get("headers", {}))

        def _get(key: str, default: str = "") -> str:
            return headers.get(key, default)

        fake_resp.headers.get = _get
        if rm["status"] == 200:
            body = rm.get("body", b"")

            async def _aiter_raw():
                yield body

            fake_resp.aiter_raw = _aiter_raw
        ctx.__aenter__ = AsyncMock(return_value=fake_resp)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

    client = MagicMock()

    def _stream(*_args, **_kwargs):
        if not queue:
            # Редирект-цикл превысил лимит — не должно случаться в тестах.
            raise AssertionError("resp_mocks queue exhausted")
        return _build_stream_ctx(queue.pop(0))

    client.stream = MagicMock(side_effect=_stream)
    client_ctx = MagicMock()
    client_ctx.__aenter__ = AsyncMock(return_value=client)
    client_ctx.__aexit__ = AsyncMock(return_value=None)
    return client_ctx, client


# ── _derive_remote_filename ───────────────────────────────────────────────────


class TestDeriveRemoteFilename:
    def test_keeps_basename_with_valid_ext(self):
        from app.api.kb.media import _derive_remote_filename

        assert (
            _derive_remote_filename("https://site.com/path/photo.png", "image/png") == "photo.png"
        )

    def test_fallback_ext_from_content_type(self):
        from app.api.kb.media import _derive_remote_filename

        # URL без расширения → берём ext из Content-Type.
        name = _derive_remote_filename("https://site.com/avatar", "image/jpeg")
        assert name == "image.jpg"

    def test_sanitizes_unsafe_chars(self):
        from app.api.kb.media import _derive_remote_filename

        name = _derive_remote_filename("https://site.com/../etc/../x.png", "image/png")
        assert name.endswith(".png")
        assert "/" not in name and ".." not in name

    def test_dot_only_basename_ignored(self):
        from app.api.kb.media import _derive_remote_filename

        # ".htaccess"-подобное имя → fallback, не отдаём скрытый файл.
        assert _derive_remote_filename("https://site.com/.gif", "image/gif") == "image.gif"


# ── save_bytes_to_path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSaveBytesToPath:
    async def test_rejects_oversize(self, tmp_path):
        from app.core.uploads import save_bytes_to_path

        with pytest.raises(HTTPException) as exc:
            await save_bytes_to_path(
                b"x" * 10, tmp_path, ("out.bin",), max_size=5, allowed_mimes=set()
            )
        assert exc.value.status_code == 413
        assert not (tmp_path / "out.bin").exists()

    async def test_rejects_disallowed_mime(self, tmp_path):
        from app.core.uploads import save_bytes_to_path

        with patch("app.core.uploads.magic") as mock_magic:
            mock_magic.from_buffer.return_value = "text/html"
            with pytest.raises(HTTPException) as exc:
                await save_bytes_to_path(
                    b"data",
                    tmp_path,
                    ("out.bin",),
                    max_size=100,
                    allowed_mimes={"image/png"},
                )
        assert exc.value.status_code == 422
        assert not (tmp_path / "out.bin").exists()

    async def test_writes_when_valid(self, tmp_path):
        from app.core.uploads import save_bytes_to_path

        written, _detected = await save_bytes_to_path(
            b"hello", tmp_path, ("sub", "out.bin"), max_size=100, allowed_mimes=None
        )
        assert written == 5
        assert (tmp_path / "sub" / "out.bin").read_bytes() == b"hello"
        # detected зависит от libmagic; в CI/без magic может быть None — не фиксируем.

    async def test_rejects_path_escape(self, tmp_path):
        """rel_segments с .. — safe_join_within блокирует (path-traversal guard)."""
        from app.core.uploads import save_bytes_to_path

        with pytest.raises(HTTPException) as exc:
            await save_bytes_to_path(
                b"hello", tmp_path, ("..", "escape.bin"), max_size=100, allowed_mimes=None
            )
        assert exc.value.status_code == 404


# ── Endpoint: SSRF / fetch behavior ───────────────────────────────────────────


@pytest.fixture
def _patched_article_and_perm():
    """Обходим БД: article-lookup и permission-check всегда ок (editor).

    SSRF/fetch-логика изолируется от БД-слоя — тестируем только сетевую часть.
    """
    article = SimpleNamespace(id=uuid.uuid4())
    with (
        patch(
            "app.api.kb.media._get_article_or_404",
            new=AsyncMock(return_value=article),
        ),
        patch(
            "app.api.kb.media.require_article_permission",
            new=AsyncMock(return_value=None),
        ),
    ):
        yield article


@pytest.mark.asyncio
class TestUploadRemoteMediaSsrf:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/x.png",
            "http://10.0.0.1/x.png",
            "http://192.168.1.1/x.png",
            "http://172.16.0.1/x.png",
            "http://169.254.169.254/latest/meta-data/x.png",
            "http://localhost/x.png",
            "http://0.0.0.0/x.png",
            "http://[::1]/x.png",
        ],
    )
    async def test_blocked_ranges_return_422_without_fetch(
        self, url, _patched_article_and_perm, tmp_path
    ):
        """Реальная SSRF-валидация: private/loopback/cloud-metadata → 422 без запроса.

        assert_url_safe НЕ патчим — проверяем настоящую блокировку в
        _fetch_remote_image. ``httpx.AsyncClient`` мокаем, чтобы убедиться, что
        сетевой запрос (``client.stream``) не уходит: early-check срабатывает в
        цикле до первого stream-вызова. (Конструктор клиента вызывается всегда —
        это паттерн ``async with httpx.AsyncClient(...)``; блокировка — внутри
        тела, поэтому проверяем именно отсутствие ``stream``-вызова.)
        """
        user = _make_user()
        app = _build_app(user, _make_redis(), kb_media_dir=tmp_path)
        client_ctx, client = _make_streaming_client(
            [{"status": 200, "headers": {"content-type": "image/png"}, "body": b"x"}]
        )
        with patch("httpx.AsyncClient", return_value=client_ctx):
            resp = await _post_remote(app, _patched_article_and_perm.id, url)
        assert resp.status_code == 422
        client.stream.assert_not_called()

    async def test_redirect_to_private_blocked(self, _patched_article_and_perm, tmp_path):
        """Первый GET отдаёт 302 → http://127.0.0.1/; второй запрос не уходит."""
        user = _make_user()
        app = _build_app(user, _make_redis(), kb_media_dir=tmp_path)

        client_ctx, client = _make_streaming_client(
            [{"status": 302, "headers": {"location": "http://127.0.0.1/admin.png"}}]
        )

        with (
            patch(_SSRF_PATCH, new=AsyncMock(side_effect=lambda u: "127.0.0.1" not in u)),
            patch(_RESOLVE_PATCH, new=AsyncMock(return_value="1.2.3.4")),
            patch("httpx.AsyncClient", return_value=client_ctx),
        ):
            resp = await _post_remote(
                app, _patched_article_and_perm.id, "https://legit.example.com/a.png"
            )
        assert resp.status_code == 422
        # Второй запрос на private не ушёл — stream вызван ровно один раз.
        assert client.stream.call_count == 1

    async def test_dns_rebinding_blocked(self, _patched_article_and_perm, tmp_path):
        """resolve_stable_ip → None → 422 без сетевого запроса."""
        user = _make_user()
        app = _build_app(user, _make_redis(), kb_media_dir=tmp_path)

        client_ctx, client = _make_streaming_client(
            [{"status": 200, "headers": {"content-type": "image/png"}, "body": b"x"}]
        )
        with (
            patch(_SSRF_PATCH, new=AsyncMock(return_value=True)),
            patch(_RESOLVE_PATCH, new=AsyncMock(return_value=None)),
            patch("httpx.AsyncClient", return_value=client_ctx),
        ):
            resp = await _post_remote(
                app, _patched_article_and_perm.id, "https://rebind.example.com/a.png"
            )
        assert resp.status_code == 422
        client.stream.assert_not_called()

    async def test_non_image_content_type_rejected(self, _patched_article_and_perm, tmp_path):
        user = _make_user()
        app = _build_app(user, _make_redis(), kb_media_dir=tmp_path)

        client_ctx, _client = _make_streaming_client(
            [
                {
                    "status": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": b"<html>",
                }
            ]
        )

        with (
            patch(_SSRF_PATCH, new=AsyncMock(return_value=True)),
            patch(_RESOLVE_PATCH, new=AsyncMock(return_value="1.2.3.4")),
            patch("httpx.AsyncClient", return_value=client_ctx),
        ):
            resp = await _post_remote(
                app, _patched_article_and_perm.id, "https://site.example.com/page"
            )
        assert resp.status_code == 422

    async def test_oversize_via_content_length(self, _patched_article_and_perm, tmp_path):
        user = _make_user()
        app = _build_app(user, _make_redis(), kb_media_dir=tmp_path)

        client_ctx, _client = _make_streaming_client(
            [
                {
                    "status": 200,
                    "headers": {"content-type": "image/png", "content-length": "999999999"},
                    "body": b"",
                }
            ]
        )

        with (
            patch(_SSRF_PATCH, new=AsyncMock(return_value=True)),
            patch(_RESOLVE_PATCH, new=AsyncMock(return_value="1.2.3.4")),
            patch("httpx.AsyncClient", return_value=client_ctx),
        ):
            resp = await _post_remote(
                app, _patched_article_and_perm.id, "https://site.example.com/big.png"
            )
        assert resp.status_code == 413

    async def test_happy_path(self, _patched_article_and_perm, tmp_path):
        """Валидные PNG-bytes → 201, URL вида /api/v1/kb/media/{id}/{name}, файл записан."""
        user = _make_user()
        app = _build_app(user, _make_redis(), kb_media_dir=tmp_path)

        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # заголовок PNG + мусор

        with (
            patch("app.api.kb.media.KB_MEDIA_DIR", tmp_path),
            patch(
                _FETCH_PATCH,
                new=AsyncMock(return_value=(png_bytes, "image/png")),
            ),
            patch("app.core.uploads.magic") as mock_magic,
        ):
            mock_magic.from_buffer.return_value = "image/png"
            resp = await _post_remote(
                app, _patched_article_and_perm.id, "https://site.example.com/photo.png"
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["url"].startswith(f"/api/v1/kb/media/{_patched_article_and_perm.id}/")
        assert body["filename"].endswith(".png")
        # Файл записан на диск.
        written = list((tmp_path / str(_patched_article_and_perm.id)).glob("*.png"))
        assert len(written) == 1
        assert written[0].read_bytes() == png_bytes


# ── Endpoint: rights & validation ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestUploadRemoteMediaRights:
    async def test_non_editor_forbidden(self, tmp_path):
        """require_article_permission поднимает 403 → endpoint не вызывает fetch."""
        from fastapi import HTTPException, status

        user = _make_user(role="reader")
        app = _build_app(user, _make_redis(), kb_media_dir=tmp_path)
        article = SimpleNamespace(id=uuid.uuid4())

        with (
            patch(
                "app.api.kb.media._get_article_or_404",
                new=AsyncMock(return_value=article),
            ),
            patch(
                "app.api.kb.media.require_article_permission",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Insufficient KB permissions",
                    )
                ),
            ),
            patch(_FETCH_PATCH, new=AsyncMock()) as mock_fetch,
        ):
            resp = await _post_remote(app, article.id, "https://site.example.com/x.png")
        assert resp.status_code == 403
        mock_fetch.assert_not_called()

    async def test_invalid_scheme_rejected(self, tmp_path):
        """ftp:// — не проходит pydantic-валидацию → 422 до endpoint-логики."""
        user = _make_user()
        app = _build_app(user, _make_redis(), kb_media_dir=tmp_path)
        resp = await _post_remote(app, uuid.uuid4(), "ftp://site.example.com/x.png")
        assert resp.status_code == 422
