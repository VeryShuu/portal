from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_booking(
    room_email: str | None = "room@x.com",
    invited_emails: list[str] | None = None,
    series_id: uuid.UUID | None = None,
    organizer_name: str = "Organiser",
    description: str | None = None,
    rooms_with_links: list[tuple[str, str]] | None = None,
):
    if rooms_with_links:

        def _make_room(name, link):
            room = SimpleNamespace(name=name, email=None, link=link)
            return SimpleNamespace(room=room)

        room_objs = [_make_room(name, link) for name, link in rooms_with_links]
    else:
        room = SimpleNamespace(name="Room A", email=room_email, link=None)
        room_objs = [SimpleNamespace(room=room)]

    booking = SimpleNamespace(
        id=uuid.uuid4(),
        title="Test Meeting",
        description=description,
        organizer_name=organizer_name,
        start_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
        series_id=series_id,
        recurrence_rule=None,
        update_count=0,
        rooms=room_objs,
        invited_users=[
            {"user_id": str(uuid.uuid4()), "full_name": "Alice", "email": addr}
            for addr in (invited_emails or [])
        ],
        creator_id=uuid.uuid4(),
    )
    return booking


def _ical_builder_mock() -> ModuleType:
    mod = ModuleType("app.services.meetings.ical_builder")
    mod.build_ical = MagicMock(return_value=b"VCAL")  # type: ignore[attr-defined]
    return mod


def _make_session_cm():
    db_mock = AsyncMock()
    db_mock.__aenter__ = AsyncMock(return_value=db_mock)
    db_mock.__aexit__ = AsyncMock(return_value=None)
    db_mock.get = AsyncMock(return_value=None)

    begin_mock = AsyncMock()
    begin_mock.__aenter__ = AsyncMock()
    begin_mock.__aexit__ = AsyncMock()
    db_mock.begin = MagicMock(return_value=begin_mock)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=db_mock)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    return session_cm, db_mock


class TestLoadOrganizer:
    async def test_no_creator_id_returns_none(self):
        from app.services.meetings.notifications import _load_organizer

        booking = SimpleNamespace(id=uuid.uuid4(), creator_id=None)
        session = AsyncMock()
        result = await _load_organizer(session, booking)
        assert result is None
        session.get.assert_not_called()

    async def test_creator_id_fetches_user(self):
        from app.services.meetings.notifications import _load_organizer

        user = SimpleNamespace(id=uuid.uuid4(), email="org@test.com")
        session = AsyncMock()
        session.get = AsyncMock(return_value=user)
        booking = SimpleNamespace(id=uuid.uuid4(), creator_id=user.id)
        result = await _load_organizer(session, booking)
        assert result is user

    async def test_exception_returns_none(self):
        from app.services.meetings.notifications import _load_organizer

        session = AsyncMock()
        session.get = AsyncMock(side_effect=RuntimeError("db error"))
        booking = SimpleNamespace(id=uuid.uuid4(), creator_id=uuid.uuid4())
        result = await _load_organizer(session, booking)
        assert result is None


class TestEnqueueOrganizer:
    async def test_none_organizer_is_noop(self):
        from app.services.meetings.notifications import _enqueue_organizer

        session = AsyncMock()
        booking = SimpleNamespace(id=uuid.uuid4())
        with patch("app.services.email_outbox.enqueue_outbox_email", AsyncMock()) as m:
            await _enqueue_organizer(session, booking, None, "REQUEST", b"VCAL", set())
        m.assert_not_awaited()

    async def test_empty_email_is_noop(self):
        from app.services.meetings.notifications import _enqueue_organizer

        session = AsyncMock()
        booking = SimpleNamespace(id=uuid.uuid4(), title="T")
        organizer = SimpleNamespace(email="", full_name="Name", notify_email=True)
        with patch("app.services.email_outbox.enqueue_outbox_email", AsyncMock()) as m:
            await _enqueue_organizer(session, booking, organizer, "REQUEST", b"VCAL", set())
        m.assert_not_awaited()

    async def test_already_sent_is_skipped(self):
        from app.services.meetings.notifications import _enqueue_organizer

        session = AsyncMock()
        booking = SimpleNamespace(id=uuid.uuid4(), title="T")
        organizer = SimpleNamespace(email="org@test.com", full_name="Org", notify_email=True)
        with patch("app.services.email_outbox.enqueue_outbox_email", AsyncMock()) as m:
            await _enqueue_organizer(
                session, booking, organizer, "REQUEST", b"VCAL", {"org@test.com"}
            )
        m.assert_not_awaited()

    async def test_notify_email_false_skipped(self):
        from app.services.meetings.notifications import _enqueue_organizer

        session = AsyncMock()
        booking = SimpleNamespace(id=uuid.uuid4(), title="T")
        organizer = SimpleNamespace(email="org@test.com", full_name="Org", notify_email=False)
        with patch("app.services.email_outbox.enqueue_outbox_email", AsyncMock()) as m:
            await _enqueue_organizer(session, booking, organizer, "REQUEST", b"VCAL", set())
        m.assert_not_awaited()

    async def test_enqueues_and_adds_to_already_sent(self):
        from app.services.meetings.notifications import _enqueue_organizer

        session = AsyncMock()
        booking = SimpleNamespace(
            id=uuid.uuid4(),
            title="T",
            description=None,
            organizer_name="Org",
            start_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
            rooms=[],
            invited_users=[],
        )
        organizer = SimpleNamespace(email="org@test.com", full_name="Org", notify_email=True)
        already_sent: set[str] = set()

        enqueue_mock = AsyncMock()
        with (
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
            patch(
                "app.core.system_config.load_system_settings",
                return_value=SimpleNamespace(timezone="UTC"),
            ),
        ):
            await _enqueue_organizer(session, booking, organizer, "REQUEST", b"VCAL", already_sent)
        assert "org@test.com" in already_sent


class TestEnqueue:
    async def test_empty_email_is_noop(self):
        from app.services.meetings.notifications import _enqueue

        session = AsyncMock()
        booking = SimpleNamespace(id=uuid.uuid4(), title="T")
        with patch("app.services.email_outbox.enqueue_outbox_email", AsyncMock()) as m:
            await _enqueue(session, booking, {"email": ""}, "REQUEST", b"VCAL")
        m.assert_not_awaited()

    async def test_enqueues_valid_email(self):
        from app.services.meetings.notifications import _enqueue

        session = AsyncMock()
        booking = SimpleNamespace(
            id=uuid.uuid4(),
            title="T",
            description=None,
            organizer_name="Org",
            start_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
            rooms=[],
            invited_users=[],
        )
        enqueue_mock = AsyncMock()
        with (
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
            patch(
                "app.core.system_config.load_system_settings",
                return_value=SimpleNamespace(timezone="UTC"),
            ),
        ):
            await _enqueue(session, booking, {"email": "user@test.com"}, "REQUEST", b"VCAL")
        enqueue_mock.assert_awaited_once()

    async def test_exception_is_caught(self):
        from app.services.meetings.notifications import _enqueue

        session = AsyncMock()
        booking = SimpleNamespace(
            id=uuid.uuid4(),
            title="T",
            description=None,
            organizer_name="Org",
            start_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
            rooms=[],
            invited_users=[],
        )
        with (
            patch(
                "app.services.email_outbox.enqueue_outbox_email",
                AsyncMock(side_effect=RuntimeError("fail")),
            ),
            patch(
                "app.core.system_config.load_system_settings",
                return_value=SimpleNamespace(timezone="UTC"),
            ),
        ):
            await _enqueue(session, booking, {"email": "user@test.com"}, "REQUEST", b"VCAL")


class TestBuildSubject:
    def test_cancel_method(self):
        from app.services.meetings.notifications import _build_subject

        booking = SimpleNamespace(title="My Meeting")
        subject = _build_subject(booking, "CANCEL")
        assert "Отменена" in subject
        assert "My Meeting" in subject

    def test_request_method(self):
        from app.services.meetings.notifications import _build_subject

        booking = SimpleNamespace(title="My Meeting")
        subject = _build_subject(booking, "REQUEST")
        assert "Приглашение" in subject
        assert "My Meeting" in subject

    def test_plain_text_title_not_html_escaped(self):
        from app.services.meetings.notifications import _build_subject

        booking = SimpleNamespace(title="R&D <sync>")
        subject = _build_subject(booking, "REQUEST")
        assert "R&D <sync>" in subject
        assert "&amp;" not in subject
        assert "&lt;" not in subject


class TestBuildHtmlBody:
    def test_cancel_shows_cancel_header(self):
        from app.services.meetings.notifications import _build_html_body

        booking = _make_booking()
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=SimpleNamespace(timezone="UTC"),
        ):
            html = _build_html_body(booking, "CANCEL")
        assert "отменена" in html.lower() or "Отменена" in html

    def test_request_shows_invite_header(self):
        from app.services.meetings.notifications import _build_html_body

        booking = _make_booking()
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=SimpleNamespace(timezone="UTC"),
        ):
            html = _build_html_body(booking, "REQUEST")
        assert "Приглашение" in html

    def test_description_included_when_present(self):
        from app.services.meetings.notifications import _build_html_body

        booking = _make_booking(description="Test description here")
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=SimpleNamespace(timezone="UTC"),
        ):
            html = _build_html_body(booking, "REQUEST")
        assert "Test description here" in html

    def test_no_description_not_shown(self):
        from app.services.meetings.notifications import _build_html_body

        booking = _make_booking(description=None)
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=SimpleNamespace(timezone="UTC"),
        ):
            html = _build_html_body(booking, "REQUEST")
        assert "<strong>Описание:</strong>" not in html

    def test_invited_users_shown(self):
        from app.services.meetings.notifications import _build_html_body

        booking = _make_booking()
        booking.invited_users = [
            {"user_id": "1", "full_name": "Alice Smith", "email": "alice@test.com"}
        ]
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=SimpleNamespace(timezone="UTC"),
        ):
            html = _build_html_body(booking, "REQUEST")
        assert "Alice Smith" in html

    def test_rooms_with_links_shown(self):
        from app.services.meetings.notifications import _build_html_body

        booking = _make_booking(rooms_with_links=[("Room 1", "https://meet.example.com")])
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=SimpleNamespace(timezone="UTC"),
        ):
            html = _build_html_body(booking, "REQUEST")
        assert "https://meet.example.com" in html

    def test_naive_datetimes_handled(self):
        from app.services.meetings.notifications import _build_html_body

        booking = _make_booking()
        booking.start_time = datetime(2026, 6, 1, 10, 0)
        booking.end_time = datetime(2026, 6, 1, 11, 0)
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=SimpleNamespace(timezone="UTC"),
        ):
            html = _build_html_body(booking, "REQUEST")
        assert "Test Meeting" in html


class TestGetFromEmail:
    def test_returns_default_when_no_file(self):
        from app.services.meetings import notifications as notif

        notif._get_from_email.__dict__.clear()
        with patch("app.services.email_settings.read_email_settings", return_value=None):
            result = notif._get_from_email()
        assert result == "portal@company.local"

    def test_reads_from_address_from_file(self):
        from app.schemas.branding import EmailSettings
        from app.services.meetings import notifications as notif

        notif._get_from_email.__dict__.clear()
        with patch(
            "app.services.email_settings.read_email_settings",
            return_value=EmailSettings(from_address="custom@company.com"),
        ):
            result = notif._get_from_email()
        assert result == "custom@company.com"

    def test_uses_cache_on_second_call(self):
        import time

        from app.services.meetings import notifications as notif

        notif._get_from_email.__dict__.clear()
        notif._get_from_email.__dict__["value"] = "cached@example.com"
        notif._get_from_email.__dict__["fetched_at"] = time.monotonic()

        result = notif._get_from_email()
        assert result == "cached@example.com"

    def test_exception_returns_default(self):
        from app.services.meetings import notifications as notif

        notif._get_from_email.__dict__.clear()
        with patch("app.services.email_settings.read_email_settings", return_value=None):
            result = notif._get_from_email()
        assert result == "portal@company.local"


class TestDispatchMeetingEmailsUpdated:
    @pytest.fixture(autouse=True)
    def _patch_ical_builder(self):
        mock_mod = _ical_builder_mock()
        with patch.dict(sys.modules, {"app.services.meetings.ical_builder": mock_mod}):
            yield mock_mod

    @pytest.fixture(autouse=True)
    def _patch_system_cfg(self):
        cfg = SimpleNamespace(
            portal_base_url="https://portal.local", timezone="Europe/Moscow", log_level="INFO"
        )
        with patch("app.core.system_config.load_system_settings", return_value=cfg):
            yield

    @pytest.fixture(autouse=True)
    def _patch_from_email(self):
        with patch(
            "app.services.meetings.notifications._get_from_email", return_value="portal@c.local"
        ):
            yield

    @pytest.fixture
    def mock_db_and_enqueue(self):
        enqueue_mock = AsyncMock()
        session_cm, db_mock = _make_session_cm()

        with (
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
        ):
            yield enqueue_mock, db_mock

    async def test_updated_with_added_users(self, mock_db_and_enqueue):
        from app.schemas.meetings import InvitedUser
        from app.services.meetings.bookings_service import BookingDiff
        from app.services.meetings.notifications import dispatch_meeting_emails

        enqueue_mock, _ = mock_db_and_enqueue
        booking = _make_booking()
        new_user = InvitedUser(
            user_id=str(uuid.uuid4()), full_name="New User", email="new@test.com"
        )
        diff = BookingDiff(added_users=[new_user])

        await dispatch_meeting_emails(booking=booking, action="updated", diff=diff)

        to_emails = [c.kwargs.get("to_email") for c in enqueue_mock.call_args_list]
        assert "new@test.com" in to_emails

    async def test_updated_with_removed_users(self, mock_db_and_enqueue):
        from app.schemas.meetings import InvitedUser
        from app.services.meetings.bookings_service import BookingDiff
        from app.services.meetings.notifications import dispatch_meeting_emails

        enqueue_mock, _ = mock_db_and_enqueue
        booking = _make_booking()
        removed_user = InvitedUser(
            user_id=str(uuid.uuid4()), full_name="Removed", email="removed@test.com"
        )
        diff = BookingDiff(removed_users=[removed_user])

        await dispatch_meeting_emails(booking=booking, action="updated", diff=diff)

        to_emails = [c.kwargs.get("to_email") for c in enqueue_mock.call_args_list]
        assert "removed@test.com" in to_emails

    async def test_updated_with_unchanged_users_non_participant_changed(self, mock_db_and_enqueue):
        from app.schemas.meetings import InvitedUser
        from app.services.meetings.bookings_service import BookingDiff
        from app.services.meetings.notifications import dispatch_meeting_emails

        enqueue_mock, _ = mock_db_and_enqueue
        booking = _make_booking()
        unchanged_user = InvitedUser(
            user_id=str(uuid.uuid4()), full_name="Unchanged", email="unchanged@test.com"
        )
        diff = BookingDiff(unchanged_users=[unchanged_user], non_participant_changed=True)

        await dispatch_meeting_emails(booking=booking, action="updated", diff=diff)

        to_emails = [c.kwargs.get("to_email") for c in enqueue_mock.call_args_list]
        assert "unchanged@test.com" in to_emails

    async def test_updated_with_old_series_uid(self, mock_db_and_enqueue):
        from app.services.meetings.bookings_service import BookingDiff
        from app.services.meetings.notifications import dispatch_meeting_emails

        enqueue_mock, _ = mock_db_and_enqueue
        series_id = uuid.uuid4()
        booking = _make_booking(series_id=series_id, invited_emails=["user@test.com"])
        diff = BookingDiff(old_series_uid=f"series-{series_id}@portal.local")

        await dispatch_meeting_emails(booking=booking, action="updated", diff=diff)

        assert enqueue_mock.call_count >= 1

    async def test_updated_diff_none_only_sends_to_organizer_and_room(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        enqueue_mock, _ = mock_db_and_enqueue
        booking = _make_booking(room_email="room@x.com")

        await dispatch_meeting_emails(booking=booking, action="updated", diff=None)

        to_emails = [c.kwargs.get("to_email") for c in enqueue_mock.call_args_list]
        assert "room@x.com" in to_emails

    async def test_created_with_invited_users(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        enqueue_mock, _ = mock_db_and_enqueue
        booking = _make_booking(invited_emails=["invited@test.com"])

        await dispatch_meeting_emails(booking=booking, action="created")

        to_emails = [c.kwargs.get("to_email") for c in enqueue_mock.call_args_list]
        assert "invited@test.com" in to_emails

    async def test_organizer_notified_when_not_invited(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        enqueue_mock, db_mock = mock_db_and_enqueue
        organizer = SimpleNamespace(
            email="organizer@test.com", full_name="Organizer", notify_email=True
        )
        db_mock.get = AsyncMock(return_value=organizer)

        booking = _make_booking()

        await dispatch_meeting_emails(booking=booking, action="created")

        to_emails = [c.kwargs.get("to_email") for c in enqueue_mock.call_args_list]
        assert "organizer@test.com" in to_emails
