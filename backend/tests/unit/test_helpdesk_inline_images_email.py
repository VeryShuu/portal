"""Unit-тесты встраивания inline-картинок rich-редактора в исходящее письмо.

``_embed_helpdesk_inline_images`` — извлекает ``<img src="/api/v1/helpdesk/...">``
из HTML, читает файлы с диска, переписывает ``src`` на ``cid:``.
``_build_helpdesk_mime`` — оборачивает тело в ``multipart/related`` при наличии
inline-картинок.

Покрывает: rewrite src→cid, дедупликацию (одна картинка多次), missing-file
best-effort (src остаётся URL), неподдерживаемый формат, отсутствие картинок.
"""

from __future__ import annotations

from email import message_from_bytes
from email.message import Message
from typing import cast
from unittest.mock import patch

import pytest

from app.worker.tasks.email_outbox import (
    _build_helpdesk_mime,
    _embed_helpdesk_inline_images,
)

_CFG = {"from_address": "portal@company.local", "host": "smtp.company.local"}


def _img_html(url: str) -> str:
    return f'<p>Ответ</p><figure><img src="{url}" alt="скрин"/></figure>'


class TestEmbedInlineImages:
    """Прямые тесты хелпера ``_embed_helpdesk_inline_images``."""

    @pytest.mark.asyncio
    async def test_rewrites_src_to_cid(self, tmp_path) -> None:
        img_path = tmp_path / "TKT-123" / "inline" / "abc_screenshot.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\x89PNG fake png data")

        url = "/api/v1/helpdesk/tickets/00000000-0000-0000-0000-000000000123/inline-media/abc_screenshot.png"
        html = _img_html(url)

        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            new_html, images = await _embed_helpdesk_inline_images(html, 123)

        assert 'src="cid:img-' in new_html
        assert url not in new_html
        assert len(images) == 1
        assert images[0]["mime"] == "image/png"
        assert images[0]["cid"].startswith("img-")
        # b64 декодируется обратно в исходные байты.
        import base64

        assert base64.b64decode(images[0]["b64"]) == b"\x89PNG fake png data"

    @pytest.mark.asyncio
    async def test_rewrites_absolute_url_to_cid(self, tmp_path) -> None:
        """``_absolutize_img_src`` (email_template.py) делает URL абсолютным
        (``https://portal.local/api/v1/...``) перед отправкой в outbox. Regex
        обязан матчить оба варианта — иначе cid-встраивание не сработает на
        реальном отправляемом письме (баг, выявленный на TKT-675)."""
        img_path = tmp_path / "TKT-123" / "inline" / "shot.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"png")

        url = "https://portal.local/api/v1/helpdesk/tickets/abc-123/inline-media/shot.png"
        html = _img_html(url)

        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            new_html, images = await _embed_helpdesk_inline_images(html, 123)

        assert 'src="cid:img-' in new_html
        assert "portal.local" not in new_html
        assert len(images) == 1

    @pytest.mark.asyncio
    async def test_dedup_same_image_referenced_twice(self, tmp_path) -> None:
        img_path = tmp_path / "TKT-123" / "inline" / "x_img.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"png-bytes")

        url = "/api/v1/helpdesk/tickets/abc/inline-media/x_img.png"
        html = f'<img src="{url}"/><p>текст</p><img src="{url}"/>'

        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            new_html, images = await _embed_helpdesk_inline_images(html, 123)

        # Одна запись inline_image (дедуп), обе ссылки переписаны на один cid.
        assert len(images) == 1
        cid = images[0]["cid"]
        assert new_html.count(f"cid:{cid}") == 2

    @pytest.mark.asyncio
    async def test_missing_file_keeps_relative_url(self, tmp_path) -> None:
        # Файла нет на диске → src остаётся относительным URL (best-effort).
        (tmp_path / "TKT-123" / "inline").mkdir(parents=True)
        url = "/api/v1/helpdesk/tickets/abc/inline-media/nonexistent.png"
        html = _img_html(url)

        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            new_html, images = await _embed_helpdesk_inline_images(html, 123)

        assert url in new_html  # не переписано
        assert "cid:" not in new_html
        assert images == []

    @pytest.mark.asyncio
    async def test_unsupported_format_skipped(self, tmp_path) -> None:
        # SVG inline-media невозможен (не в allowlist media.py), но проверяем
        # что хелпер не упадёт на незнакомом расширении в URL.
        url = "/api/v1/helpdesk/tickets/abc/inline-media/pic.svg"
        html = _img_html(url)

        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            new_html, images = await _embed_helpdesk_inline_images(html, 123)

        assert url in new_html  # не переписано
        assert images == []

    @pytest.mark.asyncio
    async def test_no_images_returns_html_unchanged(self) -> None:
        html = "<p>Простой ответ без картинок</p>"
        new_html, images = await _embed_helpdesk_inline_images(html, 123)
        assert new_html == html
        assert images == []

    @pytest.mark.asyncio
    async def test_empty_html_returns_empty(self) -> None:
        new_html, images = await _embed_helpdesk_inline_images("", 123)
        assert new_html == ""
        assert images == []

    @pytest.mark.asyncio
    async def test_mixed_readable_and_missing(self, tmp_path) -> None:
        # Одна картинка есть, вторая — нет. Читаемая → cid, пропавшая → URL.
        ok_path = tmp_path / "TKT-123" / "inline" / "ok_img.png"
        ok_path.parent.mkdir(parents=True)
        ok_path.write_bytes(b"ok")

        ok_url = "/api/v1/helpdesk/tickets/abc/inline-media/ok_img.png"
        bad_url = "/api/v1/helpdesk/tickets/abc/inline-media/bad_img.png"
        html = f'<img src="{ok_url}"/><img src="{bad_url}"/>'

        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            new_html, images = await _embed_helpdesk_inline_images(html, 123)

        assert len(images) == 1  # только читаемая
        assert "cid:" in new_html
        assert bad_url in new_html  # пропавшая осталась URL


class TestBuildMimeWithInlineImages:
    """End-to-end: ``_build_helpdesk_mime`` собирает multipart/related."""

    @pytest.mark.asyncio
    async def test_related_structure_when_inline_present(self, tmp_path) -> None:
        img_path = tmp_path / "TKT-123" / "inline" / "shot.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\x89PNG\r\n\x1a\n fake")

        url = "/api/v1/helpdesk/tickets/00000000-0000-0000-0000-000000000123/inline-media/shot.png"
        row = {
            "to_email": "client@company.local",
            "subject": "[#TKT-123] test",
            "body_html": f'<p>Смотри скрин:</p><img src="{url}"/>',
            "body_text": "Смотри скрин",
            "payload": {
                "ticket_number": 123,
                "support_domain": "company.local",
                "support_address": "portal@company.local",
                "message_id_header": "<tkn-123-x@company.local>",
                "in_reply_to": None,
                "references": [],
                "subject_original": "test",
                "attachments": [],
            },
        }

        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            msg = await _build_helpdesk_mime(row, _CFG)

        assert msg.get_content_type() == "multipart/related"
        # Внутри related — alternative (plain+html), плюс image-часть с Content-ID.
        payload = msg.get_payload()
        # ``Message.get_payload() → str | list[Message | str] | bytes`` (typeshed).
        # mypy не сужает по ``len()``/индексам списка, поэтому явный isinstance
        # на список + cast на элементы-Message (в рантайме builder кладёт Message).
        assert isinstance(payload, list)
        assert len(payload) == 2
        alt_part = cast(Message, payload[0])
        assert alt_part.get_content_type() == "multipart/alternative"
        # Вторая часть — картинка.
        img_part = cast(Message, payload[1])
        assert img_part.get_content_type() == "image/png"
        cid = img_part.get("Content-ID", "")
        assert cid.startswith("<img-") and cid.endswith(">")
        # HTML внутри содержит ссылку на тот же cid.
        alt_payload = alt_part.get_payload()
        assert isinstance(alt_payload, list)
        html_part = cast(Message, alt_payload[1])
        html_raw = html_part.get_payload(decode=True)
        assert isinstance(html_raw, (bytes, bytearray))
        assert f"cid:{cid.strip('<>')}" in html_raw.decode("utf-8")

    @pytest.mark.asyncio
    async def test_no_related_when_no_inline_images(self) -> None:
        # Письмо без картинок → обычный multipart/alternative.
        row = {
            "to_email": "client@company.local",
            "subject": "[#TKT-123] test",
            "body_html": "<p>Простой ответ</p>",
            "body_text": "Простой ответ",
            "payload": {
                "ticket_number": 123,
                "support_domain": "company.local",
                "support_address": "portal@company.local",
                "message_id_header": "<tkn-123-x@company.local>",
                "in_reply_to": None,
                "references": [],
                "subject_original": "test",
                "attachments": [],
            },
        }
        msg = await _build_helpdesk_mime(row, _CFG)
        assert msg.get_content_type() == "multipart/alternative"
        assert msg.get("Content-ID") is None

    @pytest.mark.asyncio
    async def test_related_inside_mixed_when_both_inline_and_attachment(self, tmp_path) -> None:
        # Картинка inline + обычное вложение → multipart/mixed > related > alternative.
        img_path = tmp_path / "TKT-123" / "inline" / "shot.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"png")
        att_path = tmp_path / "TKT-123" / "doc_file.pdf"
        att_path.write_bytes(b"%PDF-1.4 fake")

        url = "/api/v1/helpdesk/tickets/abc/inline-media/shot.png"
        row = {
            "to_email": "client@company.local",
            "subject": "[#TKT-123] test",
            "body_html": f'<img src="{url}"/>',
            "body_text": "txt",
            "payload": {
                "ticket_number": 123,
                "support_domain": "company.local",
                "support_address": "portal@company.local",
                "message_id_header": "<tkn-123-x@company.local>",
                "in_reply_to": None,
                "references": [],
                "subject_original": "test",
                "attachments": [
                    {
                        "filename": "doc_file.pdf",
                        "content_type": "application/pdf",
                        "original_name": "Документ.pdf",
                    }
                ],
            },
        }

        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            msg = await _build_helpdesk_mime(row, _CFG)

        assert msg.get_content_type() == "multipart/mixed"
        mixed_payload = msg.get_payload()
        assert isinstance(mixed_payload, list)
        assert len(mixed_payload) == 2
        # 1-я часть — related (тело + inline-картинка).
        assert cast(Message, mixed_payload[0]).get_content_type() == "multipart/related"
        # 2-я часть — обычное вложение (attachment).
        assert cast(Message, mixed_payload[1]).get_content_type() == "application/pdf"

    @pytest.mark.asyncio
    async def test_roundtrip_serializable(self, tmp_path) -> None:
        # Готовое сообщение корректно сериализуется и парсится email-парсером.
        img_path = tmp_path / "TKT-123" / "inline" / "shot.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\x89PNG fake")

        url = "/api/v1/helpdesk/tickets/abc/inline-media/shot.png"
        row = {
            "to_email": "client@company.local",
            "subject": "[#TKT-123] test",
            "body_html": f'<img src="{url}"/>',
            "body_text": "txt",
            "payload": {
                "ticket_number": 123,
                "support_domain": "company.local",
                "support_address": "portal@company.local",
                "message_id_header": "<tkn-123-x@company.local>",
                "in_reply_to": None,
                "references": [],
                "subject_original": "test",
                "attachments": [],
            },
        }
        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            msg = await _build_helpdesk_mime(row, _CFG)
        raw = msg.as_bytes()
        reparsed = message_from_bytes(raw)
        assert reparsed.get_content_type() == "multipart/related"
