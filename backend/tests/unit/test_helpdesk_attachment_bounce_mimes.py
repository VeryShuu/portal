"""Accept-MIME для bounce-вложений (NDN / пересланные письма).

Регрессия письма от Pantina (01.08.2026): ``message/delivery-status`` (тело NDN
Postfix) и ``text/rfc822-headers`` (вложенные заголовки) отбрасывались
``save_image_bytes`` — ``python-magic`` определяет их как ``message/rfc822``,
которого не было в ``HELPDESK_ATTACHMENT_ALLOWED_MIMES``. В результате агент
терял суть заявки (помимо обрезанного forward-блока). См. ``ingress._ingest_message``.
"""

from __future__ import annotations

from app.core.constants import HELPDESK_ATTACHMENT_ALLOWED_MIMES


class TestBounceMimesAllowed:
    def test_message_rfc822_allowed(self) -> None:
        """``message/rfc822`` — magic так определяет ``text/rfc822-headers`` и
        вложенные RFC822-тела из bounce (``Undelivered Message Headers.txt``)."""
        assert "message/rfc822" in HELPDESK_ATTACHMENT_ALLOWED_MIMES

    def test_message_delivery_status_allowed(self) -> None:
        """``message/delivery-status`` — Postfix NDN ``details.txt``
        (``Reporting-MTA`` / ``Final-Recipient`` / ``Diagnostic-Code``)."""
        assert "message/delivery-status" in HELPDESK_ATTACHMENT_ALLOWED_MIMES

    def test_text_plain_still_allowed(self) -> None:
        """``text/plain`` — ``message/delivery-status`` часто определяется magic
        именно как ``text/plain`` (нет магических байтов). Должен оставаться
        в allow-list (как и до фикса)."""
        assert "text/plain" in HELPDESK_ATTACHMENT_ALLOWED_MIMES
