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


def _extract_to_emails(enqueue_mock) -> list[str]:
    return [call.kwargs.get("to_email") for call in enqueue_mock.call_args_list]


def _ical_builder_mock() -> ModuleType:
    mod = ModuleType("app.services.meetings.ical_builder")
    mod.build_ical = MagicMock(return_value=b"VCAL")
    return mod


class TestRoomEmailDispatch:
    @pytest.fixture(autouse=True)
    def _patch_ical_builder(self):
        mock_mod = _ical_builder_mock()
        with patch.dict(sys.modules, {"app.services.meetings.ical_builder": mock_mod}):
            yield mock_mod

    @pytest.fixture(autouse=True)
    def _patch_system_cfg(self):
        cfg = SimpleNamespace(portal_base_url="https://portal.local", timezone="Europe/Moscow", log_level="INFO")
        with patch("app.core.system_config.load_system_settings", return_value=cfg):
            yield

    @pytest.fixture(autouse=True)
    def _patch_from_email(self):
        with patch("app.services.meetings.notifications._get_from_email", return_value="portal@c.local"):
            yield

    @pytest.fixture
    def mock_db_and_enqueue(self):
        enqueue_mock = AsyncMock()
        db_mock = AsyncMock()
        db_mock.__aenter__ = AsyncMock(return_value=db_mock)
        db_mock.__aexit__ = AsyncMock(return_value=None)
        
        begin_mock = AsyncMock()
        begin_mock.__aenter__ = AsyncMock()
        begin_mock.__aexit__ = AsyncMock()
        db_mock.begin = MagicMock(return_value=begin_mock)
        
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db_mock)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
        ):
            yield enqueue_mock

    async def test_created_sends_to_room_email(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        await dispatch_meeting_emails(booking=booking, action="created")

        to_emails = _extract_to_emails(mock_db_and_enqueue)
        assert "room@x.com" in to_emails

    async def test_cancelled_sends_cancel_to_room_email(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        await dispatch_meeting_emails(booking=booking, action="cancelled")

        to_emails = _extract_to_emails(mock_db_and_enqueue)
        assert "room@x.com" in to_emails

    async def test_updated_without_diff_sends_to_room_email(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        await dispatch_meeting_emails(booking=booking, action="updated", diff=None)

        to_emails = _extract_to_emails(mock_db_and_enqueue)
        assert "room@x.com" in to_emails

    async def test_no_duplicate_when_room_email_in_invited(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com", invited_emails=["room@x.com"])
        await dispatch_meeting_emails(booking=booking, action="created")

        to_emails = _extract_to_emails(mock_db_and_enqueue)
        assert to_emails.count("room@x.com") == 1

    async def test_no_room_email_skipped(self, mock_db_and_enqueue):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email=None)
        await dispatch_meeting_emails(booking=booking, action="created")

        assert mock_db_and_enqueue.call_count == 0


class TestScheduleEmailDispatch:
    async def test_schedule_email_dispatch_adds_task(self):
        from fastapi import BackgroundTasks

        from app.services.meetings.dispatch import schedule_email_dispatch

        request = MagicMock()
        booking = _make_booking()
        background = BackgroundTasks()

        with patch("app.services.meetings.notifications.dispatch_meeting_emails", new=AsyncMock()) as mock_dispatch:
            schedule_email_dispatch(background, request, booking, "created")
            assert len(background.tasks) == 1
            for task in background.tasks:
                await task()
            mock_dispatch.assert_called_once_with(booking=booking, action="created", diff=None)
