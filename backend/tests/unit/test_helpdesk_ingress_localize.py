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
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from app.core.sanitize import sanitize_html
from app.services.helpdesk.ingress import _extract_bodies, _localize_attachments_and_images


def _ticket() -> Any:
    return SimpleNamespace(id=uuid.uuid4(), number=99)


def _message() -> Any:
    return SimpleNamespace(id=uuid.uuid4())


def _msg_with_inline_and_attachment() -> Any:
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

        async def _save(
            db,
            *,
            ticket,
            message_id,
            data,
            original_name,
            total_tracker=None,
            is_inline=False,
            content_id=None,
            declared_content_type=None,
            rejection_sink=None,
        ):
            att = SimpleNamespace(id=att_id)
            saved.append((original_name, data, is_inline, content_id))
            return att

        with (
            patch(
                "app.services.helpdesk.attachments.save_image_bytes",
                new=_save,
            ),
            patch(
                "app.services.helpdesk.email_images._fetch_remote",
                new=AsyncMock(return_value=None),
            ),
        ):
            out, tracker = await _localize_attachments_and_images(
                cast("Any", object()),  # db — мок не использует
                msg=msg,
                ticket=_ticket(),
                message=_message(),
                body_html='<p>Текст <img src="cid:logo"></p>',
            )

        # Inline локализован.
        assert out is not None
        assert f"/api/v1/helpdesk/attachments/{att_id}" in out
        assert "cid:logo" not in out
        # Attach-часть (doc.pdf) сохранена как обычное вложение (is_inline=False),
        # inline cid:logo — как inline-картинка (is_inline=True, content_id="logo").
        assert ("doc.pdf", b"%PDF fake", False, None) in saved
        assert any(is_inline and cid == "logo" for _name, _data, is_inline, cid in saved)
        # Tracker возвращён (для cleanup при rollback — H-5).
        assert tracker is not None

    async def test_rejected_attachment_is_reported_to_agent(self) -> None:
        msg = _msg_with_inline_and_attachment()
        warnings: list[str] = []

        async def _reject(*_args, rejection_sink=None, **_kwargs):
            if rejection_sink is not None:
                rejection_sink.append(
                    "Вложение «doc.pdf» не сохранено: неподдерживаемый тип файла."
                )
            return None

        with patch("app.services.helpdesk.attachments.save_image_bytes", new=_reject):
            await _localize_attachments_and_images(
                cast("Any", object()),
                msg=msg,
                ticket=_ticket(),
                message=_message(),
                body_html=None,
                attachment_warnings=warnings,
            )

        assert warnings == ["Вложение «doc.pdf» не сохранено: неподдерживаемый тип файла."]

    async def test_no_images_returns_html_as_is(self) -> None:
        from email.message import Message

        msg = Message()
        html = "<p>Просто текст без картинок</p>"
        out, _tracker = await _localize_attachments_and_images(
            cast("Any", object()), msg=msg, ticket=_ticket(), message=_message(), body_html=html
        )
        assert out == html

    async def test_none_html_returns_none(self) -> None:
        from email.message import Message

        msg = Message()
        out, _tracker = await _localize_attachments_and_images(
            cast("Any", object()), msg=msg, ticket=_ticket(), message=_message(), body_html=None
        )
        assert out is None

    async def test_broken_cid_left_as_is(self) -> None:
        """cid: без соответствующей inline-части остаётся в html (best-effort)."""
        from email.message import Message

        msg = Message()
        html = '<img src="cid:nonexistent">'
        out, _tracker = await _localize_attachments_and_images(
            cast("Any", object()), msg=msg, ticket=_ticket(), message=_message(), body_html=html
        )
        assert out is not None
        assert "cid:nonexistent" in out

    async def test_first_ticket_keeps_forward_files_and_exact_inline_image(self) -> None:
        """Raw MIME composition: strip signature without losing forward or files."""
        raw = (
            "From: user@mage.ru\r\nSubject: Problem\r\nMIME-Version: 1.0\r\n"
            'Content-Type: multipart/mixed; boundary="OUT"\r\n\r\n'
            "--OUT\r\nContent-Type: multipart/related; boundary=REL\r\n\r\n"
            "--REL\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
            "<p>Please inspect the forwarded error.</p>"
            '<table data-portal-email-signature="mage-v1"><tr><td>'
            '<img src="cid:sig"></td><td>User, +7, user@mage.ru</td></tr></table>'
            "<div>-----Original Message-----</div><p>quota exceeded</p>"
            '<img src="cid:screenshot">\r\n'
            "--REL\r\nContent-Type: image/png\r\nContent-ID: <sig>\r\n"
            'Content-Disposition: inline; filename="Mage_Ru.png"\r\n'
            "Content-Transfer-Encoding: base64\r\n\r\nc2ln\r\n"
            "--REL\r\nContent-Type: image/png\r\nContent-ID: <screenshot>\r\n"
            'Content-Disposition: inline; filename="error.png"\r\n'
            "Content-Transfer-Encoding: base64\r\n\r\nc2NyZWVuc2hvdA==\r\n"
            "--REL--\r\n"
            "--OUT\r\nContent-Type: application/pdf\r\n"
            'Content-Disposition: attachment; filename="evidence.pdf"\r\n'
            "Content-Transfer-Encoding: base64\r\n\r\nJVBERg==\r\n"
            "--OUT--\r\n"
        )
        msg = message_from_bytes(raw.encode())
        plain, intermediate_html = _extract_bodies(msg, keep_forward=True)

        assert intermediate_html is not None
        assert "-----Original Message-----" in intermediate_html
        assert "quota exceeded" in intermediate_html
        assert "User, +7" not in intermediate_html
        assert 'src="cid:screenshot"' in intermediate_html

        saved: list[tuple[str, bool, str | None]] = []

        async def _save(_db, *, original_name, is_inline=False, content_id=None, **_kwargs):
            saved.append((original_name, is_inline, content_id))
            return SimpleNamespace(id=uuid.uuid4())

        with patch("app.services.helpdesk.attachments.save_image_bytes", new=_save):
            localized, _tracker = await _localize_attachments_and_images(
                cast("Any", object()),
                msg=msg,
                ticket=_ticket(),
                message=_message(),
                body_html=intermediate_html,
            )

        persisted_html = sanitize_html(localized)
        assert "-----Original Message-----" in persisted_html
        assert "quota exceeded" in plain
        assert "cid:" not in persisted_html
        assert "/api/v1/helpdesk/attachments/" in persisted_html
        assert ("evidence.pdf", False, None) in saved
        assert ("error.png", True, "screenshot") in saved
        assert not any(name == "Mage_Ru.png" for name, _inline, _cid in saved)

    async def test_attached_forward_is_saved_as_eml_without_flattening(self) -> None:
        raw = (
            "MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=OUT\r\n\r\n"
            "--OUT\r\nContent-Type: text/plain\r\n\r\nSee attached thread.\r\n"
            "--OUT\r\nContent-Type: message/rfc822\r\n"
            'Content-Disposition: attachment; filename="thread.eml"\r\n\r\n'
            "From: first@example.com\r\nSubject: Original context\r\nMIME-Version: 1.0\r\n"
            "Content-Type: multipart/mixed; boundary=INNER\r\n\r\n"
            "--INNER\r\nContent-Type: text/plain\r\n\r\nImportant forwarded text.\r\n"
            "--INNER\r\nContent-Type: application/pdf\r\n"
            'Content-Disposition: attachment; filename="inside.pdf"\r\n'
            "Content-Transfer-Encoding: base64\r\n\r\nJVBERg==\r\n"
            "--INNER--\r\n--OUT--\r\n"
        )
        msg = message_from_bytes(raw.encode())
        saved: list[tuple[str, bytes, str | None]] = []

        async def _save(_db, *, original_name, data, declared_content_type=None, **_kwargs):
            saved.append((original_name, data, declared_content_type))
            return SimpleNamespace(id=uuid.uuid4())

        with patch("app.services.helpdesk.attachments.save_image_bytes", new=_save):
            await _localize_attachments_and_images(
                cast("Any", object()),
                msg=msg,
                ticket=_ticket(),
                message=_message(),
                body_html=None,
            )

        assert [name for name, _data, _mime in saved] == ["thread.eml"]
        assert saved[0][2] == "message/rfc822"
        assert b"Important forwarded text" in saved[0][1]
        assert b"inside.pdf" in saved[0][1]
