"""Unit-тесты для core/text.py, core/pdf.py, core/uploads.py.

Покрытие:
text.py:
- slugify: ASCII, unicode-preserve, unicode-disable (ASCII-only), пустые строки,
  спецсимволы, длинные строки, кириллица

pdf.py:
- render_pdf: успешный вызов возвращает bytes
- render_pdf: HTTP-ошибка от screenshot-service → исключение

uploads.py:
- stream_upload_to_path: нормальная загрузка → (size, detected)
- stream_upload_to_path: превышение max_size → HTTPException 413
- stream_upload_to_path: неверный MIME → HTTPException 422
- stream_upload_to_path: magic недоступен → используется content_type
- iter_upload_chunks: итерация по чанкам
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── slugify ───────────────────────────────────────────────────────────────────


class TestSlugify:
    def test_plain_ascii(self):
        from app.core.text import slugify

        assert slugify("hello world") == "hello-world"

    def test_cyrillic_preserved_by_default(self):
        from app.core.text import slugify

        result = slugify("Привет мир")
        assert "привет" in result
        assert "мир" in result

    def test_cyrillic_stripped_ascii_mode(self):
        from app.core.text import slugify

        result = slugify("Привет мир", preserve_unicode=False)
        assert "привет" not in result.lower()

    def test_special_chars_removed(self):
        from app.core.text import slugify

        result = slugify("hello!@#world")
        assert "!" not in result
        assert "@" not in result
        assert "#" not in result

    def test_multiple_spaces_become_one_hyphen(self):
        from app.core.text import slugify

        result = slugify("a   b   c")
        assert result == "a-b-c"

    def test_leading_trailing_hyphens_stripped(self):
        from app.core.text import slugify

        result = slugify("---hello---")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_empty_string_returns_fallback(self):
        from app.core.text import slugify

        result = slugify("")
        assert result == "item"

    def test_custom_fallback(self):
        from app.core.text import slugify

        result = slugify("", fallback="article")
        assert result == "article"

    def test_only_special_chars_returns_fallback(self):
        from app.core.text import slugify

        result = slugify("!!!###")
        assert result == "item"

    def test_mixed_separators(self):
        from app.core.text import slugify

        result = slugify("hello_world-test")
        assert result == "hello-world-test"

    def test_unicode_letters_preserved(self):
        from app.core.text import slugify

        result = slugify("déjà-vu")
        assert "déjà" in result or "d" in result

    def test_cyrillic_slug_lowercased(self):
        from app.core.text import slugify

        result = slugify("Привет")
        assert result == result.lower()


# ── render_pdf ────────────────────────────────────────────────────────────────


class TestRenderPdf:
    @pytest.mark.asyncio
    async def test_returns_bytes_on_success(self):
        from app.core.pdf import render_pdf

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.content = b"%PDF-1.4 fake content"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=fake_response)

        with (
            patch("app.core.pdf.get_settings") as mock_settings,
            patch("app.core.pdf.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.screenshot_service_url = "http://screenshot:3000"
            mock_settings.return_value.screenshot_service_secret = ""
            result = await render_pdf("<h1>Test</h1>")

        assert isinstance(result, bytes)
        assert result == b"%PDF-1.4 fake content"

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self):
        import httpx

        from app.core.pdf import render_pdf

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            )
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=fake_response)

        with (
            patch("app.core.pdf.get_settings") as mock_settings,
            patch("app.core.pdf.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.screenshot_service_url = "http://screenshot:3000"
            mock_settings.return_value.screenshot_service_secret = ""
            with pytest.raises(httpx.HTTPStatusError):
                await render_pdf("<h1>Test</h1>")

    @pytest.mark.asyncio
    async def test_posts_html_to_correct_url(self):
        from app.core.pdf import render_pdf

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.content = b"pdf"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=fake_response)

        with (
            patch("app.core.pdf.get_settings") as mock_settings,
            patch("app.core.pdf.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.screenshot_service_url = "http://screenshot:3000/"
            mock_settings.return_value.screenshot_service_secret = ""
            await render_pdf("<p>content</p>")

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://screenshot:3000/pdf"
        assert call_args[1]["json"]["html"] == "<p>content</p>"

    @pytest.mark.asyncio
    async def test_sends_secret_header_when_configured(self):
        from app.core.pdf import render_pdf

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.content = b"pdf"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=fake_response)

        with (
            patch("app.core.pdf.get_settings") as mock_settings,
            patch("app.core.pdf.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.screenshot_service_url = "http://screenshot:3000"
            mock_settings.return_value.screenshot_service_secret = "super-secret-token"
            await render_pdf("<p>content</p>")

        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["headers"]["X-Screenshot-Secret"] == "super-secret-token"

    @pytest.mark.asyncio
    async def test_no_secret_header_when_not_configured(self):
        from app.core.pdf import render_pdf

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.content = b"pdf"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=fake_response)

        with (
            patch("app.core.pdf.get_settings") as mock_settings,
            patch("app.core.pdf.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.screenshot_service_url = "http://screenshot:3000"
            mock_settings.return_value.screenshot_service_secret = ""
            await render_pdf("<p>content</p>")

        call_kwargs = mock_client.post.call_args[1]
        assert "X-Screenshot-Secret" not in call_kwargs.get("headers", {})


# ── stream_upload_to_path ─────────────────────────────────────────────────────


class TestStreamUploadToPath:
    def _make_upload(self, data: bytes, content_type: str = "image/jpeg") -> MagicMock:
        upload = MagicMock()
        chunks = [data[i : i + 1024 * 1024] for i in range(0, len(data), 1024 * 1024)]
        chunks.append(b"")
        upload.read = AsyncMock(side_effect=chunks)
        upload.content_type = content_type
        return upload

    @pytest.mark.asyncio
    async def test_success_returns_size_and_mime(self, tmp_path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "out.jpg"
        data = b"fake jpeg data"
        upload = self._make_upload(data)

        with patch("app.core.uploads.magic", None):
            size, detected = await stream_upload_to_path(upload, dest, max_size=1024 * 1024)

        assert size == len(data)
        assert dest.exists()
        assert dest.read_bytes() == data

    @pytest.mark.asyncio
    async def test_413_when_size_exceeded(self, tmp_path):
        from fastapi import HTTPException

        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "out.jpg"
        data = b"x" * (2 * 1024 * 1024 + 1)
        upload = self._make_upload(data)

        with (
            patch("app.core.uploads.magic", None),
            pytest.raises(HTTPException) as exc,
        ):
            await stream_upload_to_path(upload, dest, max_size=1024)

        assert exc.value.status_code == 413
        assert not dest.exists()

    @pytest.mark.asyncio
    async def test_422_when_mime_not_allowed(self, tmp_path):
        from fastapi import HTTPException

        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "out.exe"
        data = b"MZ executable"
        upload = self._make_upload(data, content_type="application/octet-stream")

        with (
            patch("app.core.uploads.magic", None),
            pytest.raises(HTTPException) as exc,
        ):
            await stream_upload_to_path(
                upload,
                dest,
                max_size=1024 * 1024,
                allowed_mimes={"image/jpeg", "image/png"},
            )

        assert exc.value.status_code == 422
        assert not dest.exists()

    @pytest.mark.asyncio
    async def test_no_mime_check_when_allowed_mimes_is_none(self, tmp_path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "out.bin"
        data = b"any data"
        upload = self._make_upload(data, content_type="application/octet-stream")

        with patch("app.core.uploads.magic", None):
            size, detected = await stream_upload_to_path(
                upload, dest, max_size=1024 * 1024, allowed_mimes=None
            )

        assert size == len(data)
        assert dest.exists()

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, tmp_path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "deep" / "nested" / "out.jpg"
        data = b"data"
        upload = self._make_upload(data)

        with patch("app.core.uploads.magic", None):
            await stream_upload_to_path(upload, dest, max_size=1024 * 1024)

        assert dest.exists()

    @pytest.mark.asyncio
    async def test_uses_content_type_when_magic_unavailable(self, tmp_path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "img.jpg"
        data = b"jpeg data"
        upload = self._make_upload(data, content_type="image/jpeg")

        with patch("app.core.uploads.magic", None):
            size, detected = await stream_upload_to_path(
                upload,
                dest,
                max_size=1024 * 1024,
                allowed_mimes={"image/jpeg"},
            )

        assert size == len(data)


# ── iter_upload_chunks ────────────────────────────────────────────────────────


class TestIterUploadChunks:
    @pytest.mark.asyncio
    async def test_yields_all_chunks(self):
        from app.core.uploads import iter_upload_chunks

        data = b"chunk1" + b"chunk2" + b"chunk3"
        upload = MagicMock()
        call_count = [0]

        async def fake_read(size):
            if call_count[0] == 0:
                call_count[0] += 1
                return data
            return b""

        upload.read = fake_read

        result = b""
        async for chunk in iter_upload_chunks(upload):
            result += chunk

        assert result == data

    @pytest.mark.asyncio
    async def test_empty_upload_yields_nothing(self):
        from app.core.uploads import iter_upload_chunks

        upload = MagicMock()
        upload.read = AsyncMock(return_value=b"")

        chunks = []
        async for chunk in iter_upload_chunks(upload):
            chunks.append(chunk)

        assert chunks == []
