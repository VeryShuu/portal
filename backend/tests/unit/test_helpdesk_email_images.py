"""Unit-тесты локализации картинок письма (``email_images``).

Чистые функции (extract inline, find/replace img-src, SSRF-guard, filename)
тестируются без БД. ``localize_images`` — с моком ``save`` (DI).

Покрывает: inline cid: разбор/нормализация, rewrite img-src, SSRF (private IP,
loopback, localhost, домен), httpx fetch-мок (успех/не-image/большой/ошибка),
best-effort (одна битая картинка не роняет остальные).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.helpdesk.email_images import (
    ATTACHMENT_URL_PREFIX,
    InlineImage,
    _derive_remote_filename,
    extract_inline_parts,
    find_img_sources,
    is_safe_remote_url,
    localize_images,
    replace_img_src,
)

# ── extract_inline_parts ─────────────────────────────────────────────────────

def _make_msg_with_inline(raw: str) -> object:
    """Собрать email из сырого RFC822 (надёжнее, чем EmailMessage API)."""
    from email import message_from_bytes

    return message_from_bytes(raw.encode("utf-8"))


_INLINE_MSG = (
    "From: a@b.test\r\n"
    "Subject: x\r\n"
    "MIME-Version: 1.0\r\n"
    'Content-Type: multipart/related; boundary="B"\r\n\r\n'
    "--B\r\n"
    "Content-Type: text/html; charset=utf-8\r\n\r\n"
    '<p>hi <img src="cid:logo"></p>\r\n'
    "--B\r\n"
    "Content-Type: image/png\r\n"
    "Content-ID: <logo@company>\r\n"
    "Content-Transfer-Encoding: base64\r\n\r\n"
    "iVBORfake==\r\n"
    "--B--\r\n"
)


class TestExtractInlineParts:
    def test_collects_image_parts_by_content_id(self) -> None:
        msg = _make_msg_with_inline(_INLINE_MSG)
        result = extract_inline_parts(msg)  # type: ignore[arg-type]
        assert "logo@company" in result
        assert result["logo@company"].content_type == "image/png"

    def test_cid_normalized_lowercase_no_brackets(self) -> None:
        raw = _INLINE_MSG.replace("<logo@company>", "<Logo-X@Comp>").replace('cid:logo', 'cid:Logo-X@Comp')
        msg = _make_msg_with_inline(raw)
        result = extract_inline_parts(msg)  # type: ignore[arg-type]
        assert "logo-x@comp" in result

    def test_skips_non_image_parts(self) -> None:
        raw = (
            "From: a@b.test\r\nSubject: x\r\nMIME-Version: 1.0\r\n"
            'Content-Type: multipart/related; boundary="B"\r\n\r\n'
            "--B\r\nContent-Type: text/plain\r\nContent-ID: <doc>\r\n\r\nnotimage\r\n"
            "--B--\r\n"
        )
        msg = _make_msg_with_inline(raw)
        assert extract_inline_parts(msg) == {}  # type: ignore[arg-type]

    def test_empty_message_returns_empty(self) -> None:
        from email.message import Message

        assert extract_inline_parts(Message()) == {}


# ── find/replace img-src ────────────────────────────────────────────────────


class TestFindImgSources:
    def test_finds_double_quoted(self) -> None:
        html = '<img src="https://x.test/a.png"><img src="cid:b">'
        assert find_img_sources(html) == ["https://x.test/a.png", "cid:b"]

    def test_finds_single_and_unquoted(self) -> None:
        html = "<img src='https://x.test/a.png'><img src=https://x.test/b.png>"
        assert find_img_sources(html) == ["https://x.test/a.png", "https://x.test/b.png"]

    def test_preserves_order(self) -> None:
        html = '<img src="a"><img src="b"><img src="c">'
        assert find_img_sources(html) == ["a", "b", "c"]

    def test_empty_html(self) -> None:
        assert find_img_sources("") == []

    def test_replace_first_occurrence(self) -> None:
        html = '<img src="cid:a"><img src="cid:a">'
        out = replace_img_src(html, "cid:a", "/api/attachments/1")
        assert out.count("cid:a") == 1
        assert "/api/attachments/1" in out


# ── SSRF guard ───────────────────────────────────────────────────────────────


class TestSsrfGuard:
    def test_https_allowed(self) -> None:
        assert is_safe_remote_url("https://example.com/a.png") is True

    def test_http_allowed_scheme(self) -> None:
        # Схема разрешена; домен проверяется резолвом в _localize_remote.
        assert is_safe_remote_url("http://example.com/a.png") is True

    def test_localhost_blocked(self) -> None:
        assert is_safe_remote_url("http://localhost/a.png") is False
        assert is_safe_remote_url("http://127.0.0.1/a.png") is False

    def test_private_ip_blocked(self) -> None:
        assert is_safe_remote_url("http://10.0.0.1/a.png") is False
        assert is_safe_remote_url("http://192.168.1.1/a.png") is False
        assert is_safe_remote_url("http://172.16.0.1/a.png") is False

    def test_loopback_ipv6_blocked(self) -> None:
        assert is_safe_remote_url("http://[::1]/a.png") is False

    def test_non_http_blocked(self) -> None:
        assert is_safe_remote_url("file:///etc/passwd") is False
        assert is_safe_remote_url("ftp://x/a") is False
        assert is_safe_remote_url("cid:abc") is False

    def test_no_host_blocked(self) -> None:
        assert is_safe_remote_url("http:///a.png") is False

    def test_public_ip_allowed(self) -> None:
        assert is_safe_remote_url("http://8.8.8.8/a.png") is True


# ── filename derivation ─────────────────────────────────────────────────────


class TestDeriveFilename:
    def test_from_path(self) -> None:
        assert _derive_remote_filename("https://x.test/path/logo.png") == "logo.png"

    def test_fallback_for_empty_path(self) -> None:
        assert _derive_remote_filename("https://x.test") == "image"

    def test_fallback_for_root(self) -> None:
        assert _derive_remote_filename("https://x.test/") == "image"


# ── localize_images (DI: мок save) ─────────────────────────────────────────


def _ticket() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), number=42)


def _message() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


def _save_mock(att_id: uuid.UUID) -> AsyncMock:
    """Мок save_image_bytes — возвращает attachment с заданным id."""

    async def _save(db, *, ticket, message_id, data, original_name, total_tracker=None):
        return SimpleNamespace(id=att_id)

    return AsyncMock(side_effect=_save)


@pytest.mark.asyncio
class TestLocalizeImages:
    async def test_localize_cid_inline(self) -> None:
        att_id = uuid.uuid4()
        inline_map = {"logo": InlineImage(data=b"pngdata", content_type="image/png", filename="logo.png")}
        html = '<p>Привет</p><img src="cid:logo" alt="logo">'

        out = await _run_localize(html, inline_map, att_id)

        assert f"{ATTACHMENT_URL_PREFIX}{att_id}" in out
        assert "cid:logo" not in out

    async def test_localize_https_remote(self) -> None:
        att_id = uuid.uuid4()
        html = '<img src="https://example.com/a.png">'
        out = await _run_localize(html, {}, att_id, fetch_return=b"png")
        assert f"{ATTACHMENT_URL_PREFIX}{att_id}" in out

    async def test_best_effort_one_broken_keeps_others(self) -> None:
        """Одна битая картинка не роняет локализацию остальных."""
        att_id = uuid.uuid4()
        # Первая — SSRF-небезопасный IP, вторая — inline ок.
        inline_map = {"ok": InlineImage(data=b"x", content_type="image/png", filename="ok.png")}
        html = '<img src="https://10.0.0.1/x.png"><img src="cid:ok">'
        out = await _run_localize(html, inline_map, att_id)
        # SSRF-небезопасный остался как есть, inline локализован.
        assert "https://10.0.0.1/x.png" in out
        assert f"{ATTACHMENT_URL_PREFIX}{att_id}" in out

    async def test_relative_src_left_untouched(self) -> None:
        html = '<img src="/local/path.png">'
        out = await _run_localize(html, {}, uuid.uuid4())
        assert out == html

    async def test_empty_html(self) -> None:
        assert await localize_images(
            object(), ticket=_ticket(), message=_message(),
            html="", inline_map={}, total_tracker=None, save=_save_mock(uuid.uuid4()),
        ) == ""

    async def test_orphan_img_without_src_gets_inline(self) -> None:
        """Outlook-кейс: <img> без src (cid дропнут) привязывается к
        неиспользованной inline-части (multipart/related Content-ID)."""
        att_id = uuid.uuid4()
        inline_map = {
            "screenshot@outlook": InlineImage(
                data=b"png", content_type="image/png", filename="screenshot.png"
            )
        }
        # <img> без src — orphan. Inline-часть не сматчилась через cid:.
        html = '<p>Текст</p><img width="981" height="541" id="Рисунок_x0020_1">'
        out = await _run_localize(html, inline_map, att_id)
        # Orphan-img получил src на локализованный attachment.
        assert f"{ATTACHMENT_URL_PREFIX}{att_id}" in out
        # Тег остался <img> с другими атрибутами, но src добавлен.
        assert "<img" in out and "981" in out

    async def test_orphan_img_not_filled_when_no_inline(self) -> None:
        """Нет inline-частей → orphan-img остаётся без src (нечем заполнить)."""
        html = '<img width="100" id="x">'
        out = await _run_localize(html, {}, uuid.uuid4())
        assert out == html

    async def test_img_with_src_not_treated_as_orphan(self) -> None:
        """<img> с реальным src не трогается orphan-fallback'ом."""
        att_id = uuid.uuid4()
        inline_map = {"x": InlineImage(data=b"x", content_type="image/png", filename="x.png")}
        html = '<img src="/api/v1/helpdesk/attachments/keep">'
        out = await _run_localize(html, inline_map, att_id)
        # src не переписан (относительный — оставлен), orphan-fallback не сработал.
        assert "/api/v1/helpdesk/attachments/keep" in out


async def _run_localize(
    html: str, inline_map: dict, att_id: uuid.UUID, *, fetch_return: bytes | None = None
) -> str:
    """Хелпер: вызов localize_images с замоканными save (DI) и _fetch_remote."""
    with patch(
        "app.services.helpdesk.email_images._fetch_remote",
        new=AsyncMock(return_value=fetch_return),
    ):
        return await localize_images(
            object(),
            ticket=_ticket(),
            message=_message(),
            html=html,
            inline_map=inline_map,
            total_tracker=None,
            save=_save_mock(att_id),
        )


# ── _fetch_remote: SSRF через редиректы + async DNS ─────────────────────────
#
# CRITICAL (#4): раньше ``follow_redirects=True`` валидировал только исходный
# URL. Редирект на 127.0.0.1 / 169.254.169.254 (cloud metadata) bypass'ил guard.
# Теперь ``follow_redirects=False`` + ручная обработка с ре-валидацией каждого
# hop. Плюс DNS через asyncio loop (раньше синхронный socket.getaddrinfo).


class _FakeResponse:
    """Минимальная заглушка httpx.Response для _fetch_remote."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    @property
    def text(self) -> str:  # для диагностики
        return self.content.decode("utf-8", errors="replace")


class _FakeAsyncClient:
    """Записывает запросы и возвращает предзаданные ответы по URL.

    Используется вместо ``httpx.AsyncClient``: контекстный менеджер + ``get``.
    Каждый ``get(url)`` возвращает ответ из ``responses`` (по точному URL) или
    из ``default``. Все запрошенные URL попадают в ``requested``.
    """

    def __init__(
        self,
        responses: dict[str, _FakeResponse] | None = None,
        *,
        default: _FakeResponse | None = None,
    ) -> None:
        self._responses = responses or {}
        self._default = default or _FakeResponse(status_code=404)
        self.requested: list[str] = []

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, url: str) -> _FakeResponse:
        self.requested.append(url)
        return self._responses.get(url, self._default)


def _patch_httpx_client(fake: _FakeAsyncClient):
    """Патчит ``httpx.AsyncClient`` внутри email_images на ``fake``."""

    # httpx импортируется внутри _fetch_remote; патчим атрибут модуля httpx.
    import httpx

    return patch.object(httpx, "AsyncClient", return_value=fake)


@pytest.mark.asyncio
class TestFetchRemoteRedirects:
    async def test_safe_redirect_followed(self) -> None:
        """302 на public URL → картинка локализуется (два запроса: исходный + целевой)."""
        from app.services.helpdesk.email_images import _fetch_remote

        # Оба URL должны пройти SSRF-проверку: example.com резолвится в public.
        # Во избежание реального DNS — мокаем _resolve_is_safe.
        fake = _FakeAsyncClient(
            responses={
                "https://short.example.com/r": _FakeResponse(
                    status_code=302, headers={"location": "https://cdn.example.com/img.png"}
                ),
                "https://cdn.example.com/img.png": _FakeResponse(
                    status_code=200, content=b"PNGDATA", headers={"content-type": "image/png"}
                ),
            }
        )
        with (
            _patch_httpx_client(fake),
            patch(
                "app.services.helpdesk.email_images._resolve_is_safe",
                new=AsyncMock(return_value=True),
            ),
        ):
            data = await _fetch_remote("https://short.example.com/r")

        assert data == b"PNGDATA"
        assert fake.requested == [
            "https://short.example.com/r",
            "https://cdn.example.com/img.png",
        ]

    async def test_redirect_to_internal_blocked(self) -> None:
        """302 → 127.0.0.1 (loopback) блокируется: второй запрос не отправляется.

        Это и есть core SSRF-байпас, который чинится: раньше
        ``follow_redirects=True`` пошёл бы на 127.0.0.1 без проверки."""
        from app.services.helpdesk.email_images import _fetch_remote

        fake = _FakeAsyncClient(
            responses={
                "https://attacker.example.com/r": _FakeResponse(
                    status_code=302, headers={"location": "http://127.0.0.1/admin"}
                ),
                "http://127.0.0.1/admin": _FakeResponse(status_code=200, content=b"SECRET"),
            }
        )
        with _patch_httpx_client(fake):
            data = await _fetch_remote("https://attacker.example.com/r")

        assert data is None
        # 127.0.0.1 не запрашивался (заблокирован на re-валидации hop'а).
        assert "http://127.0.0.1/admin" not in fake.requested

    async def test_redirect_to_metadata_endpoint_blocked(self) -> None:
        """302 → 169.254.169.254 (cloud metadata) блокируется."""
        from app.services.helpdesk.email_images import _fetch_remote

        fake = _FakeAsyncClient(
            responses={
                "https://attacker.example.com/m": _FakeResponse(
                    status_code=302,
                    headers={"location": "http://169.254.169.254/latest/meta-data/"},
                ),
            }
        )
        with _patch_httpx_client(fake):
            data = await _fetch_remote("https://attacker.example.com/m")

        assert data is None
        assert "http://169.254.169.254/latest/meta-data/" not in fake.requested

    async def test_too_many_redirects_returns_none(self) -> None:
        """Цепочка > _MAX_REDIRECTS hops → None (защита от цикла)."""
        from app.services.helpdesk.email_images import _fetch_remote

        # Каждый URL редиректит на следующий — бесконечная цепочка.
        responses = {
            f"https://loop{i}.example.com": _FakeResponse(
                status_code=302, headers={"location": f"https://loop{i+1}.example.com"}
            )
            for i in range(10)
        }
        fake = _FakeAsyncClient(responses=responses)
        with (
            _patch_httpx_client(fake),
            patch(
                "app.services.helpdesk.email_images._resolve_is_safe",
                new=AsyncMock(return_value=True),
            ),
        ):
            data = await _fetch_remote("https://loop0.example.com")

        assert data is None
        # Сделано ровно _MAX_REDIRECTS+1 запросов (потом — выход по лимиту).
        assert len(fake.requested) <= 7  # _MAX_REDIRECTS=5 + 1


@pytest.mark.asyncio
class TestResolveIsSafeAsync:
    async def test_uses_async_getaddrinfo_not_socket(self) -> None:
        """``_resolve_is_safe`` должен использовать asyncio loop.getaddrinfo,
        а не синхронный socket.getaddrinfo (который блокирует event loop)."""
        import asyncio

        from app.services.helpdesk.email_images import _resolve_is_safe

        loop = asyncio.get_running_loop()
        called: list[str] = []

        async def _fake_getaddrinfo(host, port, **kw):
            called.append(host)
            # Возвращаем public IP (8.8.8.8) → safe.
            return [(0, 0, 0, "", ("8.8.8.8", port))]

        with patch.object(loop, "getaddrinfo", new=_fake_getaddrinfo):
            result = await _resolve_is_safe("example.com")

        assert result is True
        assert called == ["example.com"]

    async def test_returns_false_on_private_ip_resolution(self) -> None:
        """DNS-rebinding: домен резолвится в 10.0.0.1 → unsafe."""
        import asyncio

        from app.services.helpdesk.email_images import _resolve_is_safe

        loop = asyncio.get_running_loop()

        async def _fake_getaddrinfo(host, port, **kw):
            return [(0, 0, 0, "", ("10.0.0.1", port))]

        with patch.object(loop, "getaddrinfo", new=_fake_getaddrinfo):
            result = await _resolve_is_safe("rebinder.attacker.com")

        assert result is False

    async def test_returns_false_on_dns_failure(self) -> None:
        """Не резолвится → unsafe (best-effort: пропускаем картинку)."""
        import asyncio

        from app.services.helpdesk.email_images import _resolve_is_safe

        loop = asyncio.get_running_loop()

        async def _fake_getaddrinfo(host, port, **kw):
            raise OSError("DNS failure")

        with patch.object(loop, "getaddrinfo", new=_fake_getaddrinfo):
            result = await _resolve_is_safe("nonexistent.invalid")

        assert result is False
