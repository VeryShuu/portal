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


def _extract_to_emails(mock_enqueue_job) -> list[str]:
    return [call.kwargs["to_email"] for call in mock_enqueue_job.call_args_list]


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
        cfg = SimpleNamespace(portal_base_url="https://portal.local", timezone="Europe/Moscow")
        with patch("app.core.system_config.load_system_settings", return_value=cfg):
            yield

    @pytest.fixture(autouse=True)
    def _patch_from_email(self):
        with patch("app.services.meetings.notifications._get_from_email", return_value="portal@c.local"):
            yield

    async def test_created_sends_to_room_email(self, arq_pool):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        await dispatch_meeting_emails(arq_pool, booking=booking, action="created")

        to_emails = _extract_to_emails(arq_pool.enqueue_job)
        assert "room@x.com" in to_emails

    async def test_cancelled_sends_cancel_to_room_email(self, arq_pool):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        await dispatch_meeting_emails(arq_pool, booking=booking, action="cancelled")

        to_emails = _extract_to_emails(arq_pool.enqueue_job)
        assert "room@x.com" in to_emails

    async def test_updated_without_diff_sends_to_room_email(self, arq_pool):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com")
        await dispatch_meeting_emails(arq_pool, booking=booking, action="updated", diff=None)

        to_emails = _extract_to_emails(arq_pool.enqueue_job)
        assert "room@x.com" in to_emails

    async def test_no_duplicate_when_room_email_in_invited(self, arq_pool):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email="room@x.com", invited_emails=["room@x.com"])
        await dispatch_meeting_emails(arq_pool, booking=booking, action="created")

        to_emails = _extract_to_emails(arq_pool.enqueue_job)
        assert to_emails.count("room@x.com") == 1

    async def test_no_room_email_skipped(self, arq_pool):
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(room_email=None)
        await dispatch_meeting_emails(arq_pool, booking=booking, action="created")

        assert arq_pool.enqueue_job.call_count == 0


class TestScheduleEmailDispatch:
    async def test_dispatch_calls_enqueue_when_arq_pool_present(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from fastapi import BackgroundTasks

        from app.services.meetings.dispatch import schedule_email_dispatch

        mock_arq = AsyncMock()
        mock_arq.enqueue_job = AsyncMock()

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=mock_arq)))
        booking = _make_booking(room_email="room@x.com")

        background = BackgroundTasks()

        with patch("app.services.meetings.notifications.dispatch_meeting_emails", new=AsyncMock()) as mock_dispatch:
            schedule_email_dispatch(background, request, booking, "created")
            for task in background.tasks:
                await task()
            mock_dispatch.assert_called_once()

    async def test_dispatch_skips_when_no_arq_pool(self):
        from types import SimpleNamespace

        from fastapi import BackgroundTasks

        from app.services.meetings.dispatch import schedule_email_dispatch

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        booking = _make_booking()
        background = BackgroundTasks()
        schedule_email_dispatch(background, request, booking, "created")
        assert len(background.tasks) == 0
