"""Unit-тесты ``_localize_attachments_and_images`` (ingress) — интеграция
локализации картинок и разбора attach-частей.

Проверяет: inline cid: локализуется (src переписан), обычное вложение
(Content-Disposition: attachment) сохраняется, best-effort (битая картинка не
роняет), html без картинок возвращается как есть.
"""

from __future__ import annotations

import uuid
from email import message_from_bytes
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.helpdesk.ingress import _localize_attachments_and_images


def _ticket() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), number=99)


def _message() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


def _msg_with_inline_and_attachment() -> object:
    raw = (
        "From: a@b.test\r\n"
        "Subject: x\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="OUTER"\r\n\r\n'
        "--OUTER\r\n"
        'Content-Type: multipart/related; boundary="INNER"\r\n\r\n'
        "--INNER\r\n"
        "Content-Type: text/html; charset=utf-8\r\n\r\n"
        '<p>Текст <img src="cid:logo"></p>\r\n'
        "--INNER\r\n"
        "Content-Type: image/png\r\n"
        "Content-ID: <logo>\r\n"
        "Content-Transfer-Encoding: base64\r\n\r\n"
        "iVBORfake==\r\n"
        "--INNER--\r\n"
        "--OUTER\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="doc.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n\r\n"
        "JVBERiBmYWtl\r\n"
        "--OUTER--\r\n"
    )
    return message_from_bytes(raw.encode("utf-8"))


@pytest.mark.asyncio
class TestLocalizeAttachmentsAndImages:
    async def test_inline_image_localized_and_attachment_saved(self) -> None:
        """Inline cid: локализуется (src переписан на /api/...), attach-часть
        сохраняется через save_image_bytes (мок)."""
        att_id = uuid.uuid4()
        msg = _msg_with_inline_and_attachment()

        # save_image_bytes вызывается дважды: для attach (pdf) и для inline (png).
        # Возвращаем разные id, проверим количество вызовов.
        saved = []

        async def _save(db, *, ticket, message_id, data, original_name, total_tracker=None):
            att = SimpleNamespace(id=att_id)
            saved.append((original_name, data))
            return att

        with patch(
            "app.services.helpdesk.attachments.save_image_bytes",
            new=_save,
        ), patch(
            "app.services.helpdesk.email_images._fetch_remote",
            new=AsyncMock(return_value=None),
        ):
            out = await _localize_attachments_and_images(
                object(),  # db — мок не использует
                msg=msg,  # type: ignore[arg-type]
                ticket=_ticket(),
                message=_message(),
                body_html='<p>Текст <img src="cid:logo"></p>',
            )

        # Inline локализован.
        assert f"/api/v1/helpdesk/attachments/{att_id}" in out
        assert "cid:logo" not in out
        # Attach-часть (doc.pdf) сохранена.
        assert any(name == "doc.pdf" for name, _ in saved)

    async def test_no_images_returns_html_as_is(self) -> None:
        from email.message import Message

        msg = Message()
        html = "<p>Просто текст без картинок</p>"
        out = await _localize_attachments_and_images(
            object(), msg=msg, ticket=_ticket(), message=_message(), body_html=html
        )
        assert out == html

    async def test_none_html_returns_none(self) -> None:
        from email.message import Message

        msg = Message()
        out = await _localize_attachments_and_images(
            object(), msg=msg, ticket=_ticket(), message=_message(), body_html=None
        )
        assert out is None

    async def test_broken_cid_left_as_is(self) -> None:
        """cid: без соответствующей inline-части остаётся в html (best-effort)."""
        from email.message import Message

        msg = Message()
        html = '<img src="cid:nonexistent">'
        out = await _localize_attachments_and_images(
            object(), msg=msg, ticket=_ticket(), message=_message(), body_html=html
        )
        assert "cid:nonexistent" in out
