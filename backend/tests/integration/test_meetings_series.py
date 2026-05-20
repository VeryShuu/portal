"""Integration tests for meetings series service."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


def _slot(offset_days: int = 1) -> tuple[datetime, datetime]:
    base = (datetime.now(UTC).replace(microsecond=0)) + timedelta(days=offset_days)
    return base, base + timedelta(hours=1)


@pytest_asyncio.fixture
async def room(real_db_session):
    from app.schemas.meetings import RoomCreate
    from app.services.meetings.rooms_service import create_room

    return await create_room(
        real_db_session, RoomCreate(name=f"S-{uuid.uuid4().hex[:6]}")
    )


class TestCreateSeries:
    async def test_create_daily_series(self, real_db_session, real_user, room):
        from app.schemas.meetings import BookingCreate, RecurrenceRule
        from app.services.meetings.series_service import create_booking_series

        start, end = _slot()
        until = (start + timedelta(days=4)).date()
        bookings = await create_booking_series(
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
        assert len(bookings) == 5
        assert all(b.series_id == bookings[0].series_id for b in bookings)
        # Only the canonical (first) instance carries the RRULE.
        assert bookings[0].recurrence_rule is not None
        assert all(b.recurrence_rule is None for b in bookings[1:])

    async def test_create_weekdays_series_skips_weekend(
        self, real_db_session, real_user, room
    ):
        from app.schemas.meetings import BookingCreate, RecurrenceRule
        from app.services.meetings.series_service import create_booking_series

        # Start on a known Monday far in the future to avoid drift.
        start = datetime(2030, 1, 7, 10, 0, tzinfo=UTC)  # Monday
        end = start + timedelta(hours=1)
        until = date(2030, 1, 14)  # next Monday
        bookings = await create_booking_series(
            real_db_session,
            payload=BookingCreate(
                title="Weekdays",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq="WEEKDAYS", until_date=until),
            ),
            user=real_user,
        )
        weekdays = [b.start_time.weekday() for b in bookings]
        assert all(w < 5 for w in weekdays)


class TestUpdateAndDeleteSeries:
    async def test_count_and_delete(self, real_db_session, real_user, room):
        from app.schemas.meetings import BookingCreate, RecurrenceRule
        from app.services.meetings.bookings_service import list_bookings
        from app.services.meetings.series_service import (
            create_booking_series,
            delete_series,
            get_series_count,
        )

        start, end = _slot()
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
        series_id = bookings[0].series_id

        n = await get_series_count(real_db_session, series_id)
        assert n == len(bookings)

        snaps = await delete_series(
            real_db_session, series_id=series_id, user=real_user
        )
        assert len(snaps) == n
        assert await get_series_count(real_db_session, series_id) == 0

    async def test_update_series_renames_all(
        self, real_db_session, real_user, room
    ):
        from app.schemas.meetings import (
            BookingCreate,
            RecurrenceRule,
            SeriesUpdate,
        )
        from app.services.meetings.series_service import (
            create_booking_series,
            update_series,
        )

        start, end = _slot()
        until = (start + timedelta(days=2)).date()
        bookings = await create_booking_series(
            real_db_session,
            payload=BookingCreate(
                title="orig",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq="DAILY", until_date=until),
            ),
            user=real_user,
        )
        series_id = bookings[0].series_id

        updated, _ = await update_series(
            real_db_session,
            series_id=series_id,
            payload=SeriesUpdate(title="renamed"),
            user=real_user,
        )
        assert all(b.title == "renamed" for b in updated)
        assert all(b.update_count == 1 for b in updated)

    async def test_non_owner_cannot_update_series(
        self, real_db_session, real_user, real_editor, room
    ):
        from fastapi import HTTPException

        from app.schemas.meetings import (
            BookingCreate,
            RecurrenceRule,
            SeriesUpdate,
        )
        from app.services.meetings.series_service import (
            create_booking_series,
            update_series,
        )

        start, end = _slot()
        until = (start + timedelta(days=2)).date()
        bookings = await create_booking_series(
            real_db_session,
            payload=BookingCreate(
                title="x",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq="DAILY", until_date=until),
            ),
            user=real_user,
        )
        series_id = bookings[0].series_id
        with pytest.raises(HTTPException) as exc:
            await update_series(
                real_db_session,
                series_id=series_id,
                payload=SeriesUpdate(title="hack"),
                user=real_editor,
            )
        assert exc.value.status_code == 403

    async def test_admin_can_update_series(
        self, real_db_session, real_user, real_admin, room
    ):
        from app.schemas.meetings import (
            BookingCreate,
            RecurrenceRule,
            SeriesUpdate,
        )
        from app.services.meetings.series_service import (
            create_booking_series,
            update_series,
        )

        start, end = _slot()
        until = (start + timedelta(days=2)).date()
        bookings = await create_booking_series(
            real_db_session,
            payload=BookingCreate(
                title="x",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq="DAILY", until_date=until),
            ),
            user=real_user,
        )
        updated, _ = await update_series(
            real_db_session,
            series_id=bookings[0].series_id,
            payload=SeriesUpdate(title="admin"),
            user=real_admin,
        )
        assert updated[0].title == "admin"

    async def test_delete_missing_series_404(self, real_db_session, real_user):
        from fastapi import HTTPException

        from app.services.meetings.series_service import delete_series

        with pytest.raises(HTTPException) as exc:
            await delete_series(
                real_db_session, series_id=uuid.uuid4(), user=real_user
            )
        assert exc.value.status_code == 404


class TestUpdateSeriesTimestamp:
    async def test_update_series_shifts_time_without_changing_rooms(
        self, real_db_session, real_user, room
    ):
        from app.schemas.meetings import BookingCreate, RecurrenceRule, SeriesUpdate
        from app.services.meetings.series_service import create_booking_series, update_series

        start, end = _slot(offset_days=3)
        until = (start + timedelta(days=2)).date()
        bookings = await create_booking_series(
            real_db_session,
            payload=BookingCreate(
                title="TimeshiftTest",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq="DAILY", until_date=until),
            ),
            user=real_user,
        )
        assert len(bookings) == 3
        original_room_id = room.id
        series_id = bookings[0].series_id

        new_start = start + timedelta(hours=2)
        new_end = end + timedelta(hours=2)
        updated = await update_series(
            real_db_session,
            series_id=series_id,
            payload=SeriesUpdate(start_time=new_start, end_time=new_end),
            user=real_user,
        )

        for b in updated:
            assert b.start_time.hour == new_start.hour
            assert len(b.rooms) == 1
            assert b.rooms[0].room_id == original_room_id
