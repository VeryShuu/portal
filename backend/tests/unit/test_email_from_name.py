"""Unit-тесты отображаемого имени отправителя (email-settings from_name).

Покрывают: format_email_from (RFC 5322 display name), прокидывание from_name
в cfg воркера, заголовок From в _build_mime, CN ORGANIZER в build_ical и
email_settings_to_out.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.header import decode_header
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.branding import EmailSettings
from app.services.email_settings import email_settings_to_out, format_email_from


def _decode_from_header(value: str) -> str:
    """Декодировать RFC 2047-encoded words в From-заголовке (кириллица)."""
    return "".join(
        part.decode(charset or "utf-8") if isinstance(part, bytes) else part
        for part, charset in decode_header(value)
    )


class TestFormatEmailFrom:
    def test_name_and_address(self):
        # Не-ASCII display name кодируется RFC 2047 (=?utf-8?b?...?=) —
        # почтовые клиенты декодируют его обратно в «Портал Маге».
        out = format_email_from("Портал Маге", "portal@mage.ru")
        assert _decode_from_header(out) == "Портал Маге <portal@mage.ru>"

    def test_ascii_name_not_encoded(self):
        assert format_email_from("Portal", "portal@mage.ru") == "Portal <portal@mage.ru>"

    def test_empty_name_returns_bare_address(self):
        assert format_email_from("", "portal@mage.ru") == "portal@mage.ru"

    def test_whitespace_name_treated_as_empty(self):
        assert format_email_from("   ", "portal@mage.ru") == "portal@mage.ru"

    def test_specials_are_quoted(self):
        # Запятая в ASCII display name требует quoting (RFC 5322).
        out = format_email_from("Portal, Mage", "portal@mage.ru")
        assert out == '"Portal, Mage" <portal@mage.ru>'

    def test_empty_address_falls_back(self):
        out = format_email_from("Портал", "")
        assert _decode_from_header(out) == "Портал <portal@company.local>"


class TestSettingsRoundtrip:
    def test_to_out_includes_from_name(self):
        s = EmailSettings(host="smtp.local", from_address="portal@x", from_name="Портал")
        out = email_settings_to_out(s)
        assert out.from_name == "Портал"
        assert out.from_address == "portal@x"

    def test_from_name_defaults_to_empty(self):
        out = email_settings_to_out(EmailSettings())
        assert out.from_name == ""

    def test_from_name_length_limited(self):
        with pytest.raises(ValidationError):
            EmailSettings(from_name="x" * 256)


class TestWorkerBuildMimeFromName:
    def _cfg(self, from_name=""):
        return {"host": "smtp.example", "from_address": "portal@x.com", "from_name": from_name}

    def test_meeting_kind_uses_display_name(self):
        from app.worker.tasks.email_outbox import KIND_MEETING, _build_mime

        row = {
            "kind": KIND_MEETING,
            "to_email": "a@x.com",
            "subject": "Приглашение",
            "body_html": "<p>ok</p>",
            "body_text": None,
            "payload": {"ical_b64": "", "method": "REQUEST", "reply_to": "boss@x.com"},
        }
        msg = _build_mime(row, self._cfg(from_name="Портал Маге"))
        assert _decode_from_header(msg["From"]) == "Портал Маге <portal@x.com>"
        assert msg["Reply-To"] == "boss@x.com"

    def test_generic_kind_uses_display_name(self):
        from app.worker.tasks.email_outbox import _build_mime

        row = {
            "kind": "generic",
            "to_email": "a@x.com",
            "subject": "Привет",
            "body_html": "<p>ok</p>",
            "body_text": "ok",
            "payload": {},
        }
        msg = _build_mime(row, self._cfg(from_name="Portal"))
        assert msg["From"] == "Portal <portal@x.com>"

    def test_missing_from_name_keeps_bare_address(self):
        from app.worker.tasks.email_outbox import _build_mime

        row = {
            "kind": "generic",
            "to_email": "a@x.com",
            "subject": "Привет",
            "body_html": "<p>ok</p>",
            "body_text": None,
            "payload": {},
        }
        cfg = {"host": "smtp.example", "from_address": "portal@x.com"}
        msg = _build_mime(row, cfg)
        assert msg["From"] == "portal@x.com"


class TestIcalOrganizerCn:
    def _booking(self):
        room = SimpleNamespace(
            id=uuid4(), name="R", timezone="Europe/Moscow", link=None, email=None
        )
        return SimpleNamespace(
            id=uuid4(),
            title="T",
            organizer_name="Alice",
            description=None,
            start_time=datetime(2030, 1, 15, 7, 0, tzinfo=UTC),
            end_time=datetime(2030, 1, 15, 8, 0, tzinfo=UTC),
            invited_users=[],
            series_id=None,
            recurrence_rule=None,
            update_count=0,
            rooms=[SimpleNamespace(room=room)],
        )

    def test_organizer_cn_override(self):
        from app.services.meetings.ical_builder import build_ical

        raw = build_ical(
            self._booking(),
            "REQUEST",
            "portal.local",
            "portal@corp.local",
            organizer_cn="Портал Маге",
        ).decode("utf-8")
        text = raw.replace("\r\n ", "")  # unfold
        assert 'ORGANIZER;CN="Портал Маге":mailto:portal@corp.local' in text

    def test_organizer_cn_defaults_to_booking_name(self):
        from app.services.meetings.ical_builder import build_ical

        raw = build_ical(self._booking(), "REQUEST", "portal.local", "alice@corp.local").decode(
            "utf-8"
        )
        text = raw.replace("\r\n ", "")
        assert "ORGANIZER;CN=Alice:mailto:alice@corp.local" in text
