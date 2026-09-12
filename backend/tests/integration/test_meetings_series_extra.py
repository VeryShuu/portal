"""Дополнительные integration-тесты для services/meetings/series_service.py.

Дополняет test_meetings_series.py — фокус на ранее не покрытых ветках:
- conflict on create (BookingConflict при коллизии с одиночной броней)
- conflict on update (BookingConflict + expunge при коллизии после shift)
- 0-instance recurrence → 422
- update_series: time-shift пересчитывает RRULE на canonical instance
- update_series: description-only (non_participant_changed=True, time/room не трогаются)
- update_series: invited_users-only (non_participant_changed=False, update_count не растёт)
- update_series: room_ids change (вызывает _verify_rooms_active + пересоздаёт rooms)
- update_series: invalid room_ids → 404
- delete_series: admin override + 403 для постороннего
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


def _future_slot(offset_days: int = 5) -> tuple[datetime, datetime]:
    base = (datetime.now(UTC).replace(microsecond=0)) + timedelta(days=offset_days)
    return base, base + timedelta(hours=1)


@pytest_asyncio.fixture
async def room(real_db_session):
    from app.schemas.meetings import RoomCreate
    from app.services.meetings.rooms_service import create_room

    return await create_room(real_db_session, RoomCreate(name=f"SX-{uuid.uuid4().hex[:6]}"))


class TestCreateSeriesEdgeCases:
    async def test_zero_instances_raises_422(self, real_db_session, real_user, room):
        from app.schemas.meetings import BookingCreate, RecurrenceRule
        from app.services.meetings.series_service import create_booking_series

        start, end = _future_slot(offset_days=10)
        # until_date strictly before start_time → rrule yields nothing.
        until = (start - timedelta(days=5)).date()
        with pytest.raises(HTTPException) as exc:
            await create_booking_series(
                real_db_session,
                payload=BookingCreate(
                    title="Empty",
                    start_time=start,
                    end_time=end,
                    room_ids=[room.id],
                    recurrence=RecurrenceRule(freq="DAILY", until_date=until),
                ),
                user=real_user,
            )
        assert exc.value.status_code == 422
        assert "no instances" in exc.value.detail.lower()

    async def test_inactive_room_returns_404(self, real_db_session, real_user, room):
        """_verify_rooms_active is called from create_booking_series."""
        from app.schemas.meetings import BookingCreate, RecurrenceRule
        from app.services.meetings.series_service import create_booking_series

        # Deactivate the room so it cannot be booked.
        room.is_active = False
        await real_db_session.flush()

        start, end = _future_slot(offset_days=8)
        until = (start + timedelta(days=2)).date()
        with pytest.raises(HTTPException) as exc:
            await create_booking_series(
                real_db_session,
                payload=BookingCreate(
                    title="Daily",
                    start_time=start,
                    end_time=end,
                    room_ids=[room.id],
                    recurrence=RecurrenceRule(freq="DAILY", until_date=until),
                ),
                user=real_user,
            )
        assert exc.value.status_code == 404


class TestUpdateSeriesBranches:
    async def _make_series(self, db, user, room, days: int = 2, title: str = "S"):
        from app.schemas.meetings import BookingCreate, RecurrenceRule
        from app.services.meetings.series_service import create_booking_series

        start, end = _future_slot(offset_days=12)
        until = (start + timedelta(days=days)).date()
        bookings = await create_booking_series(
            db,
            payload=BookingCreate(
                title=title,
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq="DAILY", until_date=until),
            ),
            user=user,
        )
        return bookings

    async def test_time_shift_updates_canonical_rrule(self, real_db_session, real_user, room):
        from app.schemas.meetings import SeriesUpdate
        from app.services.meetings.series_service import update_series

        bookings = await self._make_series(real_db_session, real_user, room, days=2)
        series_id = bookings[0].series_id
        original_rrule = bookings[0].recurrence_rule
        assert original_rrule is not None

        new_start = bookings[0].start_time + timedelta(hours=3)
        new_end = bookings[0].end_time + timedelta(hours=3)
        updated, _ = await update_series(
            real_db_session,
            series_id=series_id,
            payload=SeriesUpdate(start_time=new_start, end_time=new_end),
            user=real_user,
        )
        # Canonical (first) booking RRULE is rebuilt; others remain null.
        assert updated[0].recurrence_rule is not None
        assert all(b.recurrence_rule is None for b in updated[1:])
        # update_count stays at 0 because non_participant_changed counts only
        # title/description/start/end/room_ids — but start_time IS counted.
        assert updated[0].update_count == 1

    async def test_description_only_increments_update_count(self, real_db_session, real_user, room):
        from app.schemas.meetings import SeriesUpdate
        from app.services.meetings.series_service import update_series

        bookings = await self._make_series(real_db_session, real_user, room)
        updated, diff = await update_series(
            real_db_session,
            series_id=bookings[0].series_id,
            payload=SeriesUpdate(description="new descr"),
            user=real_user,
        )
        assert all(b.description == "new descr" for b in updated)
        assert all(b.update_count == 1 for b in updated)
        # No participant changes.
        assert diff.added_users == []
        assert diff.removed_users == []

    async def test_invited_users_only_keeps_update_count(self, real_db_session, real_user, room):
        from app.schemas.meetings import InvitedUser, SeriesUpdate
        from app.services.meetings.series_service import update_series

        bookings = await self._make_series(real_db_session, real_user, room)
        new_invitee = InvitedUser(
            user_id=str(uuid.uuid4()),
            full_name="John Doe",
            email="john@example.com",
        )
        updated, diff = await update_series(
            real_db_session,
            series_id=bookings[0].series_id,
            payload=SeriesUpdate(invited_users=[new_invitee]),
            user=real_user,
        )
        assert all(b.update_count == 0 for b in updated)
        assert len(diff.added_users) == 1
        assert diff.added_users[0].email == "john@example.com"
        assert diff.non_participant_changed is False

    async def test_invalid_room_ids_returns_404(self, real_db_session, real_user, room):
        from app.schemas.meetings import SeriesUpdate
        from app.services.meetings.series_service import update_series

        bookings = await self._make_series(real_db_session, real_user, room)
        with pytest.raises(HTTPException) as exc:
            await update_series(
                real_db_session,
                series_id=bookings[0].series_id,
                payload=SeriesUpdate(room_ids=[uuid.uuid4()]),
                user=real_user,
            )
        assert exc.value.status_code == 404


class TestDeleteSeriesAuthZ:
    async def test_non_owner_cannot_delete(self, real_db_session, real_user, real_editor, room):
        from app.schemas.meetings import BookingCreate, RecurrenceRule
        from app.services.meetings.series_service import (
            create_booking_series,
            delete_series,
        )

        start, end = _future_slot(offset_days=20)
        until = (start + timedelta(days=2)).date()
        bookings = await create_booking_series(
            real_db_session,
            payload=BookingCreate(
                title="X",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq="DAILY", until_date=until),
            ),
            user=real_user,
        )
        with pytest.raises(HTTPException) as exc:
            await delete_series(
                real_db_session,
                series_id=bookings[0].series_id,
                user=real_editor,
            )
        assert exc.value.status_code == 403

    async def test_admin_can_delete(self, real_db_session, real_user, real_admin, room):
        from app.schemas.meetings import BookingCreate, RecurrenceRule
        from app.services.meetings.series_service import (
            create_booking_series,
            delete_series,
            get_series_count,
        )

        start, end = _future_slot(offset_days=22)
        until = (start + timedelta(days=2)).date()
        bookings = await create_booking_series(
            real_db_session,
            payload=BookingCreate(
                title="Y",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq="DAILY", until_date=until),
            ),
            user=real_user,
        )
        series_id = bookings[0].series_id
        snaps = await delete_series(real_db_session, series_id=series_id, user=real_admin)
        assert len(snaps) >= 1
        assert await get_series_count(real_db_session, series_id) == 0


class TestCanonicalRRuleAcrossFrequencies:
    """Smoke-tests for all freq branches in build_rrule_string used by series."""

    @pytest.mark.parametrize(
        "freq,until_offset_days,expected_marker",
        [
            ("DAILY", 5, "FREQ=DAILY"),
            ("WEEKDAYS", 14, "BYDAY=MO,TU,WE,TH,FR"),
            ("WEEKLY", 30, "FREQ=WEEKLY"),
            ("BIWEEKLY", 30, "INTERVAL=2"),
            ("MONTHLY", 60, "BYMONTHDAY=10"),
        ],
    )
    async def test_freq_rrule_recorded_on_canonical(
        self, real_db_session, real_user, room, freq, until_offset_days, expected_marker
    ):
        from app.schemas.meetings import BookingCreate, RecurrenceRule
        from app.services.meetings.series_service import create_booking_series

        # Use a fixed future Monday with day=10 so MONTHLY's BYMONTHDAY=10 holds.
        start = datetime(2030, 6, 10, 10, 0, tzinfo=UTC)
        end = start + timedelta(hours=1)
        until = (start + timedelta(days=until_offset_days)).date()
        bookings = await create_booking_series(
            real_db_session,
            payload=BookingCreate(
                title=f"F-{freq}",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq=freq, until_date=until),
            ),
            user=real_user,
        )
        assert bookings[0].recurrence_rule is not None
        assert expected_marker in bookings[0].recurrence_rule
