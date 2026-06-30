"""Unit-тесты сборки исходящего helpdesk-MIME (Этап 4, Б7).

``_build_helpdesk_mime`` — async (читает вложения с диска через aiofiles).
Покрывает канонические заголовки из ТЗ §1.3.3/§5.2: Message-ID, In-Reply-To,
References, Reply-To, Subject ``[#TKT-{number}] {original}``. Защита от
header-injection (sanitize), отказ при пустом support_domain, формат
Message-ID ``<tkn-{number}-{uuid}@{domain}>``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.worker.tasks.email_outbox import _build_helpdesk_mime

_CFG = {"from_address": "portal@company.local", "host": "smtp.company.local"}


def _row(
    *,
    ticket_number: int = 123,
    support_domain: str = "company.local",
    message_id_header: str | None = "<tkn-123-abc@company.local>",
    subject_original: str = "Не работает VPN",
    references: list[str] | None = None,
    attachments: list | None = None,
) -> dict:
    return {
        "to_email": "client@company.local",
        "subject": "[#TKT-123] Не работает VPN",
        "body_html": "<p>Ответ</p>",
        "body_text": "Ответ",
        "payload": {
            "ticket_number": ticket_number,
            "support_domain": support_domain,
            "message_id_header": message_id_header,
            "in_reply_to": references[0] if references else None,
            "references": references or [],
            "subject_original": subject_original,
            "attachments": attachments or [],
        },
    }


class TestBuildHelpdeskMimeHeaders:
    @pytest.mark.asyncio
    async def test_subject_format(self) -> None:
        msg = await _build_helpdesk_mime(_row(), _CFG)
        assert msg["Subject"] == "[#TKT-123] Не работает VPN"

    @pytest.mark.asyncio
    async def test_message_id_set(self) -> None:
        msg = await _build_helpdesk_mime(_row(), _CFG)
        assert msg["Message-ID"] == "<tkn-123-abc@company.local>"

    @pytest.mark.asyncio
    async def test_message_id_omitted_when_missing(self) -> None:
        msg = await _build_helpdesk_mime(_row(message_id_header=None), _CFG)
        assert msg.get("Message-ID") is None

    @pytest.mark.asyncio
    async def test_reply_to_subaddressing(self) -> None:
        msg = await _build_helpdesk_mime(_row(), _CFG)
        assert msg["Reply-To"] == "support+TKT-123@company.local"

    @pytest.mark.asyncio
    async def test_references_threading(self) -> None:
        refs = ["<msg-1@company.local>", "<msg-2@company.local>"]
        msg = await _build_helpdesk_mime(_row(references=refs), _CFG)
        assert msg["In-Reply-To"] == "<msg-1@company.local>"
        assert msg["References"] == "<msg-1@company.local> <msg-2@company.local>"

    @pytest.mark.asyncio
    async def test_from_to_headers(self) -> None:
        msg = await _build_helpdesk_mime(_row(), _CFG)
        assert msg["From"] == "portal@company.local"
        assert msg["To"] == "client@company.local"

    @pytest.mark.asyncio
    async def test_alternative_when_no_attachments(self) -> None:
        msg = await _build_helpdesk_mime(_row(), _CFG)
        assert msg.get_content_type() == "multipart/alternative"

    @pytest.mark.asyncio
    async def test_mixed_when_attachments(self, tmp_path) -> None:
        # Файл кладём в поддиректорию тикета, как строит путь _build_helpdesk_mime.
        ticket_dir = tmp_path / "TKT-123"
        ticket_dir.mkdir()
        (ticket_dir / "f.bin").write_bytes(b"hello")
        with patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path):
            msg = await _build_helpdesk_mime(
                _row(
                    attachments=[
                        {
                            "filename": "f.bin",
                            "original_name": "doc.pdf",
                            "content_type": "application/pdf",
                        }
                    ]
                ),
                _CFG,
            )
        assert msg.get_content_type() == "multipart/mixed"


class TestBuildHelpdeskMimeValidation:
    @pytest.mark.asyncio
    async def test_missing_support_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="support_domain"):
            await _build_helpdesk_mime(_row(support_domain=""), _CFG)

    @pytest.mark.asyncio
    async def test_missing_ticket_number_raises(self) -> None:
        with pytest.raises(ValueError, match="ticket_number"):
            await _build_helpdesk_mime(_row(ticket_number=0), _CFG)

    @pytest.mark.asyncio
    async def test_header_injection_subject_sanitized(self) -> None:
        # Header-injection — это про CRLF: sanitize схлопывает переводы строк
        # в пробел, поэтому «Bcc: ...» НЕ становится отдельным заголовком
        # (остаётся лишь текстом внутри значения Subject).
        row = _row(subject_original="тема\r\nBcc: victim@x")
        msg = await _build_helpdesk_mime(row, _CFG)
        assert "\r" not in msg["Subject"]
        assert "\n" not in msg["Subject"]
        # Отдельного заголовка Bcc не появилось — инъекция не прошла.
        assert msg.get("Bcc") is None


class TestKINDConstant:
    def test_kind_helpdesk_value(self) -> None:
        from app.services.email_outbox import KIND_HELPDESK

        assert KIND_HELPDESK == "helpdesk"
