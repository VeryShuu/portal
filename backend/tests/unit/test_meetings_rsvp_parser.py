"""Unit-тесты парсера IMIP-ответов (rsvp_parser).

Письма собираются как настоящие MIME-сообщения (multipart/mixed →
alternative → text/calendar), как их присылают Outlook/Thunderbird.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.services.meetings.rsvp_parser import parse_reply_email, parse_uid


def _reply_message(
    *,
    uid: str,
    attendee_email: str,
    partstat: str = "ACCEPTED",
    sender: str | None = None,
    method: str = "REPLY",
    recurrence_line: str = "",
    with_calendar: bool = True,
    subject: str = "Accepted: Standup",
) -> Message:
    msg = MIMEMultipart("mixed")
    msg["From"] = f"Ivanov Ivan <{sender or attendee_email}>"
    msg["To"] = "portal@c.local"
    msg["Subject"] = subject
    msg["Message-ID"] = f"<{uuid.uuid4()}@mail.mage.ru>"

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText("<p>Ivan accepted</p>", "html", "utf-8"))
    if with_calendar:
        ical = (
            "BEGIN:VCALENDAR\r\n"
            f"METHOD:{method}\r\n"
            "PRODID:-//Microsoft//Outlook//EN\r\n"
            "VERSION:2.0\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"{recurrence_line}"
            f"ATTENDEE;PARTSTAT={partstat};RSVP=TRUE:mailto:{attendee_email}\r\n"
            "ORGANIZER;CN=Portal:mailto:portal@c.local\r\n"
            "DTSTART:20260901T100000Z\r\n"
            "DTEND:20260901T110000Z\r\n"
            "SUMMARY:Standup\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        part = MIMEText(ical, "calendar", "utf-8")
        part.set_param("method", method)
        alternative.attach(part)
    msg.attach(alternative)
    return msg


def _to_bytes(msg: Message) -> bytes:
    return msg.as_bytes()


class TestParseUid:
    def test_single_booking_uid(self):
        booking_id = uuid.uuid4()
        parsed = parse_uid(f"{booking_id}@portal.mage.ru")
        assert parsed is not None and parsed.booking_id == booking_id
        assert not parsed.is_series

    def test_series_uid(self):
        series_id = uuid.uuid4()
        parsed = parse_uid(f"series-{series_id}@portal.mage.ru")
        assert parsed is not None and parsed.series_id == series_id
        assert parsed.is_series

    def test_foreign_uid_rejected(self):
        assert parse_uid("standup-42@portal.mage.ru") is None
        assert parse_uid("series-not-a-uuid@portal.mage.ru") is None
        assert parse_uid("") is None


class TestParseReplyEmail:
    def test_valid_accepted_single_booking(self):
        booking_id = uuid.uuid4()
        raw = _to_bytes(
            _reply_message(uid=f"{booking_id}@portal.mage.ru", attendee_email="Ivanov@Mage.ru")
        )
        parsed = parse_reply_email(raw)
        assert parsed is not None
        assert parsed.status == "accepted"
        assert parsed.attendee_email == "ivanov@mage.ru"  # CI-нормализация
        assert parsed.sender_email == "ivanov@mage.ru"
        assert parsed.uid == f"{booking_id}@portal.mage.ru"
        assert parsed.recurrence_id is None
        assert parsed.message_id.startswith("<")

    def test_declined_series_without_recurrence_id(self):
        series_id = uuid.uuid4()
        raw = _to_bytes(
            _reply_message(
                uid=f"series-{series_id}@portal.mage.ru",
                attendee_email="petrov@mage.ru",
                partstat="DECLINED",
            )
        )
        parsed = parse_reply_email(raw)
        assert parsed is not None and parsed.status == "declined"
        assert parsed.recurrence_id is None

    def test_recurrence_id_parsed_as_aware_datetime(self):
        series_id = uuid.uuid4()
        raw = _to_bytes(
            _reply_message(
                uid=f"series-{series_id}@portal.mage.ru",
                attendee_email="a@mage.ru",
                recurrence_line="RECURRENCE-ID;TZID=Europe/Moscow:20260901T130000\r\n",
            )
        )
        parsed = parse_reply_email(raw)
        assert parsed is not None
        assert parsed.recurrence_id is not None
        assert parsed.recurrence_id.tzinfo is not None

    def test_tentative_mapped(self):
        booking_id = uuid.uuid4()
        raw = _to_bytes(
            _reply_message(
                uid=f"{booking_id}@portal.mage.ru", attendee_email="a@mage.ru", partstat="TENTATIVE"
            )
        )
        assert parse_reply_email(raw).status == "tentative"  # type: ignore[union-attr]

    def test_sender_mismatch_rejected(self):
        """From ≠ ATTENDEE — подделка/пересылка чужого ответа, не обрабатываем."""
        booking_id = uuid.uuid4()
        raw = _to_bytes(
            _reply_message(
                uid=f"{booking_id}@portal.mage.ru",
                attendee_email="victim@mage.ru",
                sender="attacker@evil.com",
            )
        )
        assert parse_reply_email(raw) is None

    def test_non_reply_method_rejected(self):
        booking_id = uuid.uuid4()
        raw = _to_bytes(
            _reply_message(
                uid=f"{booking_id}@portal.mage.ru",
                attendee_email="a@mage.ru",
                method="REQUEST",
            )
        )
        assert parse_reply_email(raw) is None

    def test_counter_method_rejected(self):
        """«Предложить другое время» (COUNTER) — вне скоупа v1."""
        booking_id = uuid.uuid4()
        raw = _to_bytes(
            _reply_message(
                uid=f"{booking_id}@portal.mage.ru",
                attendee_email="a@mage.ru",
                method="COUNTER",
            )
        )
        assert parse_reply_email(raw) is None

    def test_plain_letter_without_calendar_rejected(self):
        """Обычное письмо общего ящика (ERP-отчёт, переписка) — не трогаем."""
        raw = _to_bytes(_reply_message(uid="x@x", attendee_email="a@mage.ru", with_calendar=False))
        assert parse_reply_email(raw) is None

    def test_unsupported_partstat_rejected(self):
        booking_id = uuid.uuid4()
        raw = _to_bytes(
            _reply_message(
                uid=f"{booking_id}@portal.mage.ru",
                attendee_email="a@mage.ru",
                partstat="NEEDS-ACTION",
            )
        )
        assert parse_reply_email(raw) is None

    def test_foreign_uid_rejected(self):
        raw = _to_bytes(_reply_message(uid="vacation-42@other.com", attendee_email="a@mage.ru"))
        assert parse_reply_email(raw) is None

    def test_garbage_bytes_do_not_raise(self):
        assert parse_reply_email(b"\xff\xfe not an email at all") is None


class TestRecurrenceTz:
    def test_utc_recurrence_id(self):
        series_id = uuid.uuid4()
        raw = _to_bytes(
            _reply_message(
                uid=f"series-{series_id}@portal.mage.ru",
                attendee_email="a@mage.ru",
                recurrence_line="RECURRENCE-ID:20260901T100000Z\r\n",
            )
        )
        parsed = parse_reply_email(raw)
        assert parsed is not None
        assert parsed.recurrence_id == datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
