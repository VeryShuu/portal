"""Unit tests for meetings notifications: room.email dispatch."""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _make_booking(room_email: str | None = "room@x.com", invited_emails: list[str] | None = None):
    room = SimpleNamespace(name="Room A", email=room_email, timezone="Europe/Moscow", link=None)
    br = SimpleNamespace(room=room)
    booking = SimpleNamespace(
        id=uuid.uuid4(),
        title="Test",
        description=None,
        organizer_name="Organiser",
        start_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
        series_id=None,
        recurrence_rule=None,
        update_count=0,
        rooms=[br],
        invited_users=[
            {"user_id": str(uuid.uuid4()), "full_name": "Alice", "email": addr}
            for addr in (invited_emails or [])
        ],
    )
    return booking


@pytest.fixture
def arq_pool():
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    return pool


def _extract_to_emails(enqueue_mock, batch_mock=None) -> list[str]:
    """Собирает to_email из single-вызовов + batch-вызовов (audit M3).

    batch_mock.call_args_list содержит вызовы ``batch(session, items)`` — items
    позиционный (args[1]); раскрываем его в плоский список emails.
    """
    emails = [call.kwargs.get("to_email") for call in enqueue_mock.call_args_list]
    if batch_mock is not None:
        for call in batch_mock.call_args_list:
            items = call.kwargs.get("items") or (call.args[1] if len(call.args) > 1 else [])
            for item in items:
                emails.append(item.to_email)
    return emails


def _ical_builder_mock() -> ModuleType:
    mod = ModuleType("app.services.meetings.ical_builder")
    mod.build_ical = MagicMock(return_value=b"VCAL")  # type: ignore[attr-defined]
    return mod


class TestRoomEmailDispatch:
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
        batch_mock = AsyncMock(return_value=[])
        db_mock = AsyncMock()
        db_mock.__aenter__ = AsyncMock(return_value=db_mock)
        db_mock.__aexit__ = AsyncMock(return_value=None)

        begin_mock = AsyncMock()
        begin_mock.__aenter__ = AsyncMock()
        begin_mock.__aexit__ = AsyncMock(return_value=None)
        db_mock.begin = MagicMock(return_value=begin_mock)

        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db_mock)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
            patch("app.services.email_outbox.enqueue_outbox_email_batch", batch_mock),
        ):
            yield enqueue_mock, batch_mock

    async def test_created_sends_to_room_email(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        await dispatch_meeting_emails(booking=booking, action="created")

        enqueue_mock, batch_mock = mock_db_and_enqueue
        to_emails = _extract_to_emails(enqueue_mock, batch_mock)
        assert "room@x.com" in to_emails

    async def test_cancelled_sends_cancel_to_room_email(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        await dispatch_meeting_emails(booking=booking, action="cancelled")

        enqueue_mock, batch_mock = mock_db_and_enqueue
        to_emails = _extract_to_emails(enqueue_mock, batch_mock)
        assert "room@x.com" in to_emails

    async def test_updated_without_diff_sends_to_room_email(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        await dispatch_meeting_emails(booking=booking, action="updated", diff=None)

        enqueue_mock, batch_mock = mock_db_and_enqueue
        to_emails = _extract_to_emails(enqueue_mock, batch_mock)
        assert "room@x.com" in to_emails

    async def test_no_duplicate_when_room_email_in_invited(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com", invited_emails=["room@x.com"])
        await dispatch_meeting_emails(booking=booking, action="created")

        enqueue_mock, batch_mock = mock_db_and_enqueue
        to_emails = _extract_to_emails(enqueue_mock, batch_mock)
        assert to_emails.count("room@x.com") == 1

    async def test_no_room_email_skipped(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email=None)
        await dispatch_meeting_emails(booking=booking, action="created")

        enqueue_mock, batch_mock = mock_db_and_enqueue
        assert enqueue_mock.call_count == 0
        assert batch_mock.call_count == 0


class TestEnqueueMeetingEmailsInSession:
    """E2: meeting emails must be enqueued in the *caller's* session so they
    commit atomically with the booking — never via a separate session/tx."""

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

    async def test_uses_passed_session_without_opening_its_own(self):
        from app.services.meetings.notifications import enqueue_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        passed_session = AsyncMock()
        enqueue_mock = AsyncMock()
        batch_mock = AsyncMock(return_value=[])
        session_local = MagicMock()

        with (
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
            patch("app.services.email_outbox.enqueue_outbox_email_batch", batch_mock),
            patch("app.core.database.AsyncSessionLocal", session_local),
        ):
            await enqueue_meeting_emails(passed_session, booking=booking, action="created")

        # No separate session/transaction is opened (outbox invariant).
        session_local.assert_not_called()
        passed_session.commit.assert_not_called()
        # The outbox rows are written through the caller-provided session —
        # и single (organizer/rooms), и batch (invited) используют passed_session.
        all_calls = enqueue_mock.call_args_list + batch_mock.call_args_list
        assert len(all_calls) >= 1
        for call in all_calls:
            assert call.args[0] is passed_session


def _invited(email: str, full_name: str = "User"):
    from app.schemas.meetings import InvitedUser

    return InvitedUser(user_id=str(uuid.uuid4()), full_name=full_name, email=email)


def _extract_to_method(enqueue_mock, batch_mock=None) -> list[tuple[str, str]]:
    """Собирает (to_email, method) из single- + batch-вызовов (audit M3).

    OutboxItem хранит payload как dict (как и single-вызов), поэтому method
    извлекается одинаково из обоих источников.
    """
    pairs = [
        (c.kwargs.get("to_email"), c.kwargs.get("payload", {}).get("method"))
        for c in enqueue_mock.call_args_list
    ]
    if batch_mock is not None:
        for call in batch_mock.call_args_list:
            items = call.kwargs.get("items") or (call.args[1] if len(call.args) > 1 else [])
            for item in items:
                pairs.append((item.to_email, (item.payload or {}).get("method")))
    return pairs


class TestUpdatedWithDiffDispatch:
    """Characterization tests for the differential 'updated' branch."""

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

    @pytest.fixture(autouse=True)
    def _patch_organizer(self):
        with patch(
            "app.services.meetings.notifications._load_organizer",
            AsyncMock(return_value=None),
        ):
            yield

    @pytest.fixture
    def enqueue_mocks(self):
        single = AsyncMock()
        batch = AsyncMock(return_value=[])
        with (
            patch("app.services.email_outbox.enqueue_outbox_email", single),
            patch("app.services.email_outbox.enqueue_outbox_email_batch", batch),
        ):
            yield single, batch

    async def test_added_users_get_request(self, enqueue_mocks):
        from app.services.meetings.bookings_service import BookingDiff
        from app.services.meetings.notifications import enqueue_meeting_emails

        booking = _make_booking(room_email=None)
        diff = BookingDiff(added_users=[_invited("new@x.com")])
        await enqueue_meeting_emails(AsyncMock(), booking=booking, action="updated", diff=diff)

        single, batch = enqueue_mocks
        assert ("new@x.com", "REQUEST") in _extract_to_method(single, batch)

    async def test_removed_users_get_cancel(self, enqueue_mocks):
        from app.services.meetings.bookings_service import BookingDiff
        from app.services.meetings.notifications import enqueue_meeting_emails

        booking = _make_booking(room_email=None)
        diff = BookingDiff(removed_users=[_invited("gone@x.com")])
        await enqueue_meeting_emails(AsyncMock(), booking=booking, action="updated", diff=diff)

        single, batch = enqueue_mocks
        assert ("gone@x.com", "CANCEL") in _extract_to_method(single, batch)

    async def test_unchanged_users_resent_only_on_non_participant_change(self, enqueue_mocks):
        from app.services.meetings.bookings_service import BookingDiff
        from app.services.meetings.notifications import enqueue_meeting_emails

        booking = _make_booking(room_email=None)
        diff = BookingDiff(unchanged_users=[_invited("same@x.com")], non_participant_changed=True)
        await enqueue_meeting_emails(AsyncMock(), booking=booking, action="updated", diff=diff)

        single, batch = enqueue_mocks
        assert ("same@x.com", "REQUEST") in _extract_to_method(single, batch)

    async def test_unchanged_users_not_resent_without_non_participant_change(self, enqueue_mocks):
        from app.services.meetings.bookings_service import BookingDiff
        from app.services.meetings.notifications import enqueue_meeting_emails

        booking = _make_booking(room_email=None)
        diff = BookingDiff(unchanged_users=[_invited("same@x.com")], non_participant_changed=False)
        await enqueue_meeting_emails(AsyncMock(), booking=booking, action="updated", diff=diff)

        single, batch = enqueue_mocks
        assert ("same@x.com", "REQUEST") not in _extract_to_method(single, batch)

    async def test_series_relink_cancels_old_uid_then_requests(
        self, enqueue_mocks, _patch_ical_builder
    ):
        from app.services.meetings.bookings_service import BookingDiff
        from app.services.meetings.notifications import enqueue_meeting_emails

        booking = _make_booking(room_email=None, invited_emails=["a@x.com"])
        diff = BookingDiff(old_series_uid="series-1@portal.local")
        await enqueue_meeting_emails(AsyncMock(), booking=booking, action="updated", diff=diff)

        single, batch = enqueue_mocks
        methods = [m for _, m in _extract_to_method(single, batch)]
        assert "CANCEL" in methods and "REQUEST" in methods
        # CANCEL (old UID) is enqueued before the new REQUEST.
        assert methods.index("CANCEL") < methods.index("REQUEST")
        # The old series UID is used for the CANCEL iCal.
        uid_calls = [
            c
            for c in _patch_ical_builder.build_ical.call_args_list
            if c.kwargs.get("uid_override") == "series-1@portal.local"
        ]
        assert uid_calls
