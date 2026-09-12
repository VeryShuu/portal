"""Unit-тесты RSVP-инджеста: чистые функции + IMAP-транспорт на фейк-клиенте."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.schemas.branding import EmailSettings
from app.services.meetings.rsvp_parser import ParsedReply

# ── Чистые функции rsvp_ingest ─────────────────────────────────────────────


class TestIngestHelpers:
    def test_fallback_message_id_stable(self):
        from app.services.meetings.rsvp_ingest import _fallback_message_id

        assert _fallback_message_id(b"abc") == _fallback_message_id(b"abc")
        assert _fallback_message_id(b"abc") != _fallback_message_id(b"abd")

    def test_as_utc_aware_passthrough(self):
        from app.services.meetings.rsvp_ingest import _as_utc

        dt = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
        assert _as_utc(dt, "Europe/Moscow") == dt

    def test_as_utc_naive_interpreted_as_portal_tz(self):
        from zoneinfo import ZoneInfo

        from app.services.meetings.rsvp_ingest import _as_utc

        naive = datetime(2026, 9, 1, 13, 0)  # 13:00 Moscow (UTC+3)
        assert _as_utc(naive, "Europe/Moscow") == datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
        assert _as_utc(naive, "Europe/Moscow").utcoffset() == ZoneInfo("UTC").utcoffset(
            datetime(2026, 9, 1, 10, 0)
        )

    def test_invited_entry_ci_match(self):
        from app.services.meetings.rsvp_ingest import _invited_entry

        booking = SimpleNamespace(
            invited_users=[{"user_id": "u1", "full_name": "A", "email": "Ivanov@Mage.ru"}]
        )
        entry = _invited_entry(booking, "ivanov@mage.ru")
        assert entry is not None and entry["full_name"] == "A"
        assert _invited_entry(booking, "other@x.com") is None

    def test_participant_user_id_uuid_and_external(self):
        from app.services.meetings.rsvp_ingest import _participant_user_id

        uid = str(uuid.uuid4())
        assert _participant_user_id({"user_id": uid}) == uuid.UUID(uid)
        assert _participant_user_id({"user_id": "ext:guest@x.com"}) is None
        assert _participant_user_id({"user_id": "garbage"}) is None
        assert _participant_user_id({}) is None


# ── Гейты поллера/дайджестов ────────────────────────────────────────────────


class TestGates:
    def _mods(self, *, enabled: bool, rsvp: bool) -> object:
        return SimpleNamespace(meetings=SimpleNamespace(enabled=enabled, rsvp_ingest_enabled=rsvp))

    def test_module_disabled(self):
        from app.worker.tasks.meetings.rsvp_poll import _gates_open

        with patch(
            "app.core.modules_config.load_modules",
            return_value=self._mods(enabled=False, rsvp=True),
        ):
            assert _gates_open() == "module_disabled"

    def test_rsvp_ingest_disabled(self):
        from app.worker.tasks.meetings.rsvp_poll import _gates_open

        with patch(
            "app.core.modules_config.load_modules",
            return_value=self._mods(enabled=True, rsvp=False),
        ):
            assert _gates_open() == "rsvp_ingest_disabled"

    def test_gates_open(self):
        from app.worker.tasks.meetings.rsvp_poll import _gates_open

        with patch(
            "app.core.modules_config.load_modules", return_value=self._mods(enabled=True, rsvp=True)
        ):
            assert _gates_open() is None

    def test_digest_gates_mirror_poll_gates(self):
        from app.worker.tasks.meetings.rsvp_digest import _gates_open

        with patch(
            "app.core.modules_config.load_modules",
            return_value=self._mods(enabled=True, rsvp=False),
        ):
            assert _gates_open() == "rsvp_ingest_disabled"
        with patch(
            "app.core.modules_config.load_modules", return_value=self._mods(enabled=True, rsvp=True)
        ):
            assert _gates_open() is None

    def test_email_target(self):
        from app.worker.tasks.meetings.rsvp_digest import _email_target

        assert _email_target(SimpleNamespace(email="a@x", notify_email=True)) == "a@x"
        assert _email_target(SimpleNamespace(email="a@x", notify_email=False)) is None
        assert _email_target(SimpleNamespace(email="", notify_email=True)) is None
        assert _email_target(None) is None


# ── IMAP-транспорт на фейк-клиенте ─────────────────────────────────────────


class _FakeImapClient:
    """Минимальный aioimaplib-двойник: SEARCH ALL + FETCH + STORE/EXPUNGE."""

    def __init__(self, messages: list[bytes]) -> None:
        self._messages = list(messages)  # IMAP-UID = index+1
        self.stored: list[str] = []
        self.expunged = False

    async def wait_hello_from_server(self) -> str:
        return "OK"

    async def login(self, user: str, password: str) -> tuple:
        return ("OK",)

    async def select(self, folder: str) -> tuple:
        return ("OK",)

    async def search(self, criteria: str) -> tuple:
        uids = " ".join(str(i + 1) for i in range(len(self._messages)))
        return ("OK", [uids.encode()])

    async def fetch(self, uid: str, spec: str) -> tuple:
        body = self._messages[int(uid) - 1]
        # literal-маркер как у aioimaplib: {NNN} перед телом письма
        return ("OK", [f"FETCH UID BODY[] {{{len(body)}}}".encode(), body])

    async def store(self, uid: str, mode: str, flags: str) -> tuple:
        self.stored.append(uid)
        return ("OK",)

    async def expunge(self) -> tuple:
        self.expunged = True
        return ("OK",)

    async def logout(self) -> None:
        return None


def _settings(imap_password: str = "secret") -> EmailSettings:
    return EmailSettings(
        host="smtp.x",
        from_address="portal@c.local",
        imap_host="imap.x",
        imap_port=993,
        imap_username="portal@c.local",
        imap_password=imap_password,
        imap_folder="INBOX",
    )


def _make_reply_raw(attendee: str = "a@mage.ru", partstat: str = "ACCEPTED") -> bytes:
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    booking_id = uuid.uuid4()
    msg = MIMEMultipart("mixed")
    msg["From"] = f"A <{attendee}>"
    msg["Message-ID"] = f"<{uuid.uuid4()}@m>"
    ical = (
        "BEGIN:VCALENDAR\r\nMETHOD:REPLY\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
        f"UID:{booking_id}@portal.mage.ru\r\n"
        f"ATTENDEE;PARTSTAT={partstat}:mailto:{attendee}\r\n"
        "ORGANIZER:mailto:portal@c.local\r\nDTSTART:20260901T100000Z\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    part = MIMEText(ical, "calendar", "utf-8")
    part.set_param("method", "REPLY")
    msg.attach(part)
    return msg.as_bytes()


class TestImapTransport:
    @pytest.mark.asyncio
    async def test_fetch_returns_only_valid_replies(self, monkeypatch):
        from app.services.meetings import rsvp_ingest

        plain = b"From: a@mage.ru\r\nSubject: ERP report\r\n\r\nhello"
        fake = _FakeImapClient([plain, _make_reply_raw()])
        monkeypatch.setattr("aioimaplib.IMAP4_SSL", lambda *, host, port: fake, raising=True)

        candidates = await rsvp_ingest.fetch_reply_candidates(_settings())
        assert len(candidates) == 1
        assert candidates[0].uid == "2"  # обычное письмо мимо, REPLY взят
        assert candidates[0].parsed.status == "accepted"
        assert candidates[0].message_id.startswith("<")

    @pytest.mark.asyncio
    async def test_fetch_no_password_returns_empty(self):
        from app.services.meetings import rsvp_ingest

        assert await rsvp_ingest.fetch_reply_candidates(_settings(imap_password="")) == []

    @pytest.mark.asyncio
    async def test_delete_marks_and_expunges(self, monkeypatch):
        from app.services.meetings import rsvp_ingest

        fake = _FakeImapClient([_make_reply_raw()])
        monkeypatch.setattr("aioimaplib.IMAP4_SSL", lambda *, host, port: fake)
        deleted = await rsvp_ingest.delete_reply_messages(_settings(), ["1"])
        assert deleted == 1
        assert fake.stored == ["1"]
        assert fake.expunged

    @pytest.mark.asyncio
    async def test_delete_empty_uids_noop(self):
        from app.services.meetings import rsvp_ingest

        assert await rsvp_ingest.delete_reply_messages(_settings(), []) == 0


class TestReplyCandidateMessageId:
    def test_fallback_when_message_id_missing(self):
        from app.services.meetings.rsvp_ingest import ReplyCandidate

        parsed = ParsedReply(
            message_id="",
            sender_email="a@x",
            attendee_email="a@x",
            status="accepted",
            uid="u@x",
            recurrence_id=None,
        )
        candidate = ReplyCandidate(uid="1", parsed=parsed, raw=b"bytes")
        assert candidate.message_id.startswith("<rsvp-")
