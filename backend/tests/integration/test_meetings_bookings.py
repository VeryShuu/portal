"""Integration tests for meetings bookings service.

Covers create / update / delete, 409 conflict on overlap, RBAC (creator vs
admin vs another user), and time/room change cascades.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


def _slot(offset_hours: int = 24) -> tuple[datetime, datetime]:
    base = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=offset_hours)
    return base, base + timedelta(hours=1)


@pytest_asyncio.fixture
async def room(real_db_session):
    from app.schemas.meetings import RoomCreate
    from app.services.meetings.rooms_service import create_room

    return await create_room(real_db_session, RoomCreate(name=f"R-{uuid.uuid4().hex[:6]}"))


@pytest_asyncio.fixture
async def room2(real_db_session):
    from app.schemas.meetings import RoomCreate
    from app.services.meetings.rooms_service import create_room

    return await create_room(real_db_session, RoomCreate(name=f"R2-{uuid.uuid4().hex[:6]}"))


class TestCreateBooking:
    async def test_create_basic(self, real_db_session, real_user, room):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import create_booking

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="Standup", start_time=start, end_time=end, room_ids=[room.id]
            ),
            user=real_user,
        )
        assert b.id is not None
        assert b.title == "Standup"
        assert b.organizer_name == real_user.full_name
        assert b.creator_id == real_user.id
        assert len(b.rooms) == 1
        assert b.rooms[0].room_id == room.id
        assert b.update_count == 0

    async def test_create_with_inactive_room_404(self, real_db_session, real_user, room):
        from fastapi import HTTPException

        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import create_booking
        from app.services.meetings.rooms_service import soft_delete_room

        await soft_delete_room(real_db_session, room)
        start, end = _slot()
        with pytest.raises(HTTPException) as exc:
            await create_booking(
                real_db_session,
                payload=BookingCreate(
                    title="x", start_time=start, end_time=end, room_ids=[room.id]
                ),
                user=real_user,
            )
        assert exc.value.status_code == 404

    async def test_overlap_raises_conflict(self, real_db_session, real_user, room):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            BookingConflict,
            create_booking,
        )

        start, end = _slot()
        await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="First", start_time=start, end_time=end, room_ids=[room.id]
            ),
            user=real_user,
        )

        overlap_start = start + timedelta(minutes=30)
        overlap_end = end + timedelta(minutes=30)
        with pytest.raises(BookingConflict):
            await create_booking(
                real_db_session,
                payload=BookingCreate(
                    title="Second",
                    start_time=overlap_start,
                    end_time=overlap_end,
                    room_ids=[room.id],
                ),
                user=real_user,
            )
        # Note: conflicts list is built via a follow-up SELECT after rollback;
        # in tests with SAVEPOINT-only isolation the rollback also unwinds the
        # first booking insert, so the list is empty. The exception itself
        # (raised by the DB EXCLUDE constraint) is the contract under test.

    async def test_adjacent_bookings_no_conflict(self, real_db_session, real_user, room):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import create_booking

        start, end = _slot()
        await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="First", start_time=start, end_time=end, room_ids=[room.id]
            ),
            user=real_user,
        )
        # Half-open range [start, end) → exact-end-as-start is allowed.
        b2 = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="Second",
                start_time=end,
                end_time=end + timedelta(hours=1),
                room_ids=[room.id],
            ),
            user=real_user,
        )
        assert b2.id is not None


class TestUpdateBooking:
    async def test_owner_can_update(self, real_db_session, real_user, room):
        from app.schemas.meetings import BookingCreate, BookingUpdate
        from app.services.meetings.bookings_service import (
            create_booking,
            update_booking,
        )

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(title="orig", start_time=start, end_time=end, room_ids=[room.id]),
            user=real_user,
        )
        updated, diff = await update_booking(
            real_db_session,
            booking_id=b.id,
            payload=BookingUpdate(title="renamed"),
            user=real_user,
        )
        assert updated.title == "renamed"
        assert updated.update_count == 1
        assert diff.non_participant_changed is True

    async def test_non_owner_non_admin_forbidden(
        self, real_db_session, real_user, real_editor, room
    ):
        from fastapi import HTTPException

        from app.schemas.meetings import BookingCreate, BookingUpdate
        from app.services.meetings.bookings_service import (
            create_booking,
            update_booking,
        )

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(title="orig", start_time=start, end_time=end, room_ids=[room.id]),
            user=real_user,
        )
        with pytest.raises(HTTPException) as exc:
            await update_booking(
                real_db_session,
                booking_id=b.id,
                payload=BookingUpdate(title="x"),
                user=real_editor,
            )
        assert exc.value.status_code == 403

    async def test_admin_can_update_others_booking(
        self, real_db_session, real_user, real_admin, room
    ):
        from app.schemas.meetings import BookingCreate, BookingUpdate
        from app.services.meetings.bookings_service import (
            create_booking,
            update_booking,
        )

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(title="orig", start_time=start, end_time=end, room_ids=[room.id]),
            user=real_user,
        )
        updated, _ = await update_booking(
            real_db_session,
            booking_id=b.id,
            payload=BookingUpdate(title="admin-fixed"),
            user=real_admin,
        )
        assert updated.title == "admin-fixed"

    async def test_update_time_with_overlap_raises_conflict(self, real_db_session, real_user, room):
        from app.schemas.meetings import BookingCreate, BookingUpdate
        from app.services.meetings.bookings_service import (
            BookingConflict,
            create_booking,
            update_booking,
        )

        start, end = _slot()
        await create_booking(
            real_db_session,
            payload=BookingCreate(title="A", start_time=start, end_time=end, room_ids=[room.id]),
            user=real_user,
        )
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="B",
                start_time=end + timedelta(hours=2),
                end_time=end + timedelta(hours=3),
                room_ids=[room.id],
            ),
            user=real_user,
        )
        with pytest.raises(BookingConflict):
            await update_booking(
                real_db_session,
                booking_id=b.id,
                payload=BookingUpdate(start_time=start, end_time=end + timedelta(minutes=15)),
                user=real_user,
            )

    async def test_participant_diff(self, real_db_session, real_user, room):
        from app.schemas.meetings import (
            BookingCreate,
            BookingUpdate,
            InvitedUser,
        )
        from app.services.meetings.bookings_service import (
            create_booking,
            update_booking,
        )

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="x",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                invited_users=[
                    InvitedUser(user_id="u1", full_name="A", email="a@x.com"),
                    InvitedUser(user_id="u2", full_name="B", email="b@x.com"),
                ],
            ),
            user=real_user,
        )
        _, diff = await update_booking(
            real_db_session,
            booking_id=b.id,
            payload=BookingUpdate(
                invited_users=[
                    InvitedUser(user_id="u2", full_name="B", email="b@x.com"),
                    InvitedUser(user_id="u3", full_name="C", email="c@x.com"),
                ]
            ),
            user=real_user,
        )
        added_ids = {u.user_id for u in diff.added_users}
        removed_ids = {u.user_id for u in diff.removed_users}
        unchanged_ids = {u.user_id for u in diff.unchanged_users}
        assert added_ids == {"u3"}
        assert removed_ids == {"u1"}
        assert unchanged_ids == {"u2"}
        assert diff.non_participant_changed is False


class TestDeleteBooking:
    async def test_owner_can_delete(self, real_db_session, real_user, room):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            create_booking,
            delete_booking,
            get_booking,
        )

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(title="x", start_time=start, end_time=end, room_ids=[room.id]),
            user=real_user,
        )
        snap = await delete_booking(real_db_session, booking_id=b.id, user=real_user)
        assert snap.id == b.id

        loaded = await get_booking(real_db_session, b.id)
        assert loaded is None

    async def test_non_owner_non_admin_cannot_delete(
        self, real_db_session, real_user, real_editor, room
    ):
        from fastapi import HTTPException

        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            create_booking,
            delete_booking,
        )

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(title="x", start_time=start, end_time=end, room_ids=[room.id]),
            user=real_user,
        )
        with pytest.raises(HTTPException) as exc:
            await delete_booking(real_db_session, booking_id=b.id, user=real_editor)
        assert exc.value.status_code == 403

    async def test_admin_can_delete_others_booking(
        self, real_db_session, real_user, real_admin, room
    ):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            create_booking,
            delete_booking,
        )

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(title="x", start_time=start, end_time=end, room_ids=[room.id]),
            user=real_user,
        )
        snap = await delete_booking(real_db_session, booking_id=b.id, user=real_admin)
        assert snap.id == b.id


class TestListBookings:
    async def test_list_filtered_by_room_and_date(self, real_db_session, real_user, room, room2):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            create_booking,
            list_bookings,
        )

        start, end = _slot()
        b1 = await create_booking(
            real_db_session,
            payload=BookingCreate(title="r1", start_time=start, end_time=end, room_ids=[room.id]),
            user=real_user,
        )
        b2 = await create_booking(
            real_db_session,
            payload=BookingCreate(title="r2", start_time=start, end_time=end, room_ids=[room2.id]),
            user=real_user,
        )

        only_room1 = await list_bookings(real_db_session, room_id=room.id)
        ids = {b.id for b in only_room1}
        assert b1.id in ids
        assert b2.id not in ids

    async def test_list_my_bookings(self, real_db_session, real_user, real_editor, room):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            create_booking,
            list_my_bookings,
        )

        start, end = _slot()
        b_mine = await create_booking(
            real_db_session,
            payload=BookingCreate(title="mine", start_time=start, end_time=end, room_ids=[room.id]),
            user=real_user,
        )
        await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="theirs",
                start_time=start + timedelta(hours=2),
                end_time=end + timedelta(hours=2),
                room_ids=[room.id],
            ),
            user=real_editor,
        )
        rows = await list_my_bookings(real_db_session, user_id=real_user.id)
        ids = {b.id for b in rows}
        assert b_mine.id in ids
        assert all(b.creator_id == real_user.id for b in rows)


class TestListBookingsTzAware:
    async def test_list_bookings_date_includes_moscow_booking(
        self, real_db_session, real_user, room
    ):
        from datetime import date as date_type
        from zoneinfo import ZoneInfo

        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import create_booking, list_bookings

        msk = ZoneInfo("Europe/Moscow")
        monday_msk = datetime(2030, 1, 7, 1, 0, tzinfo=msk)
        end_msk = monday_msk + timedelta(hours=1)

        b = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="EarlyMoscow",
                start_time=monday_msk,
                end_time=end_msk,
                room_ids=[room.id],
            ),
            user=real_user,
        )

        monday_date = date_type(2030, 1, 7)
        results = await list_bookings(
            real_db_session,
            date=monday_date,
            tz="Europe/Moscow",
        )
        ids = {booking.id for booking in results}
        assert b.id in ids

    async def test_list_bookings_date_excludes_utc_day_before(
        self, real_db_session, real_user, room
    ):
        from datetime import date as date_type
        from zoneinfo import ZoneInfo

        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import create_booking, list_bookings

        msk = ZoneInfo("Europe/Moscow")
        monday_msk = datetime(2030, 1, 7, 1, 0, tzinfo=msk)
        end_msk = monday_msk + timedelta(hours=1)

        await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="EarlyMoscowExcl",
                start_time=monday_msk,
                end_time=end_msk,
                room_ids=[room.id],
            ),
            user=real_user,
        )

        sunday_date = date_type(2030, 1, 6)
        results = await list_bookings(
            real_db_session,
            date=sunday_date,
            tz="Europe/Moscow",
        )
        assert all(b.title != "EarlyMoscowExcl" for b in results)
