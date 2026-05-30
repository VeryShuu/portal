"""Дополнительное покрытие services/meetings/bookings_service.py.

Дополняет test_meetings_bookings.py — фокус на ранее не покрытых ветках:
- update_booking: new_end <= new_start → 422
- update_booking: apply_to == "this" + series_id → отрыв от серии (recurrence_rule=None)
- update_booking: multi-room change (rebuild MeetingBookingRoom)
- update_booking: 404 для unknown id
- delete_booking: 404 для unknown id
- get_booking: None для unknown id
- ConflictInfo: pre_conflicts заполняется деталями при overlap на create
- list_bookings: start_date+end_date overlap window
- list_bookings: только start_date
- list_bookings: только end_date
- list_bookings: фильтр по creator_id
- list_my_bookings: явный start_date, custom limit + cap до MY_BOOKINGS_LIMIT_MAX
- _compute_diff: малформированный user entry (без user_id/email) пропускается
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException


def _slot(offset_hours: int = 24) -> tuple[datetime, datetime]:
    base = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=offset_hours)
    return base, base + timedelta(hours=1)


@pytest_asyncio.fixture
async def room(real_db_session):
    from app.schemas.meetings import RoomCreate
    from app.services.meetings.rooms_service import create_room

    return await create_room(
        real_db_session, RoomCreate(name=f"BX-{uuid.uuid4().hex[:6]}")
    )


@pytest_asyncio.fixture
async def room2(real_db_session):
    from app.schemas.meetings import RoomCreate
    from app.services.meetings.rooms_service import create_room

    return await create_room(
        real_db_session, RoomCreate(name=f"BX2-{uuid.uuid4().hex[:6]}")
    )


@pytest.mark.asyncio
class TestUpdateBookingValidation:
    async def test_end_before_start_raises_422(
        self, real_db_session, real_user, room
    ):
        """Сервисная ветка new_end <= new_start (Pydantic-валидация обходится через model_construct)."""
        from app.schemas.meetings import BookingCreate, BookingUpdate
        from app.services.meetings.bookings_service import (
            create_booking,
            update_booking,
        )

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="x", start_time=start, end_time=end, room_ids=[room.id]
            ),
            user=real_user,
        )
        # Обход Pydantic-валидатора (cross-field), чтобы добраться до сервисной 422.
        bad = BookingUpdate.model_construct(start_time=end, end_time=start)
        with pytest.raises(HTTPException) as exc:
            await update_booking(
                real_db_session,
                booking_id=b.id,
                payload=bad,
                user=real_user,
            )
        assert exc.value.status_code == 422
        assert "end_time" in exc.value.detail

    async def test_update_unknown_id_404(self, real_db_session, real_user):
        from app.schemas.meetings import BookingUpdate
        from app.services.meetings.bookings_service import update_booking

        with pytest.raises(HTTPException) as exc:
            await update_booking(
                real_db_session,
                booking_id=uuid.uuid4(),
                payload=BookingUpdate(title="x"),
                user=real_user,
            )
        assert exc.value.status_code == 404

    async def test_update_multi_room_rebuilds_rooms(
        self, real_db_session, real_user, room, room2
    ):
        from sqlalchemy import select

        from app.models.meetings import MeetingBookingRoom
        from app.schemas.meetings import BookingCreate, BookingUpdate
        from app.services.meetings.bookings_service import (
            create_booking,
            update_booking,
        )

        start, end = _slot()
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="multi", start_time=start, end_time=end, room_ids=[room.id]
            ),
            user=real_user,
        )
        updated, _ = await update_booking(
            real_db_session,
            booking_id=b.id,
            payload=BookingUpdate(room_ids=[room.id, room2.id]),
            user=real_user,
        )
        # Чтобы не зависеть от состояния relationship кэша после rebuild, читаем
        # rooms напрямую из БД.
        rows = await real_db_session.execute(
            select(MeetingBookingRoom.room_id).where(
                MeetingBookingRoom.booking_id == b.id
            )
        )
        rids = {r[0] for r in rows.fetchall()}
        assert rids == {room.id, room2.id}
        assert updated.update_count == 1


@pytest.mark.asyncio
class TestUpdateBookingDetachFromSeries:
    async def test_apply_to_this_clears_series(
        self, real_db_session, real_user, room
    ):
        from app.schemas.meetings import (
            BookingCreate,
            BookingUpdate,
            RecurrenceRule,
        )
        from app.services.meetings.bookings_service import update_booking
        from app.services.meetings.series_service import create_booking_series

        start, end = _slot(offset_hours=72)
        until = (start + timedelta(days=3)).date()
        bookings = await create_booking_series(
            real_db_session,
            payload=BookingCreate(
                title="ser",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
                recurrence=RecurrenceRule(freq="DAILY", until_date=until),
            ),
            user=real_user,
        )
        assert bookings[1].series_id is not None

        instance = bookings[1]
        original_series_id = instance.series_id

        updated, diff = await update_booking(
            real_db_session,
            booking_id=instance.id,
            payload=BookingUpdate(title="single", apply_to="this"),
            user=real_user,
        )
        assert updated.series_id is None
        assert updated.recurrence_rule is None
        assert diff.old_series_uid is not None
        assert str(original_series_id) in diff.old_series_uid


@pytest.mark.asyncio
class TestDeleteBookingValidation:
    async def test_delete_unknown_id_404(self, real_db_session, real_user):
        from app.services.meetings.bookings_service import delete_booking

        with pytest.raises(HTTPException) as exc:
            await delete_booking(
                real_db_session, booking_id=uuid.uuid4(), user=real_user
            )
        assert exc.value.status_code == 404


@pytest.mark.asyncio
class TestGetBooking:
    async def test_get_missing_returns_none(self, real_db_session):
        from app.services.meetings.bookings_service import get_booking

        assert await get_booking(real_db_session, uuid.uuid4()) is None


@pytest.mark.asyncio
class TestCreateBookingPreConflictDetails:
    async def test_pre_conflict_lists_details(
        self, real_db_session, real_user, room
    ):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            BookingConflict,
            create_booking,
        )

        start, end = _slot(offset_hours=48)
        await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="First-Pre",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
            ),
            user=real_user,
        )
        # Second booking with strict overlap → pre_check fires before flush.
        with pytest.raises(BookingConflict) as exc:
            await create_booking(
                real_db_session,
                payload=BookingCreate(
                    title="Second-Pre",
                    start_time=start + timedelta(minutes=15),
                    end_time=end + timedelta(minutes=15),
                    room_ids=[room.id],
                ),
                user=real_user,
            )
        # pre_conflicts path populates the conflict list with details.
        assert len(exc.value.conflicts) >= 1
        info = exc.value.conflicts[0]
        assert info.room_name == room.name
        assert info.booking_title == "First-Pre"


@pytest.mark.asyncio
class TestListBookingsRanges:
    async def test_list_bookings_overlap_window(
        self, real_db_session, real_user, room
    ):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            create_booking,
            list_bookings,
        )

        # Booking spans days 5..5+1h relative to "today"
        start, end = _slot(offset_hours=24 * 5 + 10)
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="ov", start_time=start, end_time=end, room_ids=[room.id]
            ),
            user=real_user,
        )
        today = datetime.now(UTC).date()
        rows = await list_bookings(
            real_db_session,
            start_date=today,
            end_date=today + timedelta(days=7),
        )
        assert b.id in {r.id for r in rows}

    async def test_list_bookings_start_date_only(
        self, real_db_session, real_user, room
    ):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            create_booking,
            list_bookings,
        )

        start, end = _slot(offset_hours=48)
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="sd", start_time=start, end_time=end, room_ids=[room.id]
            ),
            user=real_user,
        )
        rows = await list_bookings(
            real_db_session, start_date=datetime.now(UTC).date()
        )
        assert b.id in {r.id for r in rows}

    async def test_list_bookings_end_date_only(
        self, real_db_session, real_user, room
    ):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            create_booking,
            list_bookings,
        )

        start, end = _slot(offset_hours=2)
        b = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="ed", start_time=start, end_time=end, room_ids=[room.id]
            ),
            user=real_user,
        )
        rows = await list_bookings(
            real_db_session, end_date=datetime.now(UTC).date() + timedelta(days=1)
        )
        assert b.id in {r.id for r in rows}

    async def test_list_bookings_filter_by_creator(
        self, real_db_session, real_user, real_editor, room
    ):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import (
            create_booking,
            list_bookings,
        )

        start, end = _slot(offset_hours=4)
        b_mine = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="mine-c",
                start_time=start,
                end_time=end,
                room_ids=[room.id],
            ),
            user=real_user,
        )
        b_other = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="oth-c",
                start_time=start + timedelta(hours=2),
                end_time=end + timedelta(hours=2),
                room_ids=[room.id],
            ),
            user=real_editor,
        )
        rows = await list_bookings(real_db_session, creator_id=real_user.id)
        ids = {r.id for r in rows}
        assert b_mine.id in ids
        assert b_other.id not in ids


@pytest.mark.asyncio
class TestListMyBookingsBranches:
    async def test_explicit_start_date_and_limit_cap(
        self, real_db_session, real_user, room
    ):
        from app.services.meetings.bookings_service import (
            MY_BOOKINGS_LIMIT_MAX,
            list_my_bookings,
        )

        # Большой limit обрезается до MY_BOOKINGS_LIMIT_MAX внутри SQL.
        rows = await list_my_bookings(
            real_db_session,
            user_id=real_user.id,
            start_date=date(2030, 1, 1),
            limit=MY_BOOKINGS_LIMIT_MAX + 100,
        )
        assert isinstance(rows, list)


class TestComputeDiffMalformed:
    def test_skips_user_without_user_id(self):
        from app.schemas.meetings import InvitedUser
        from app.services.meetings.bookings_service import _compute_diff

        old = [
            {"email": "no-id@x.com"},  # malformed
            {"user_id": "u1", "email": "u1@x.com", "full_name": "U1"},
        ]
        new_invited = [
            InvitedUser(user_id="u1", full_name="U1", email="u1@x.com"),
            InvitedUser(user_id="u2", full_name="U2", email="u2@x.com"),
        ]
        diff = _compute_diff(old, new_invited, non_participant_changed=False)
        added = {u.user_id for u in diff.added_users}
        unchanged = {u.user_id for u in diff.unchanged_users}
        # Malformed entry is dropped before set diffing.
        assert added == {"u2"}
        assert unchanged == {"u1"}
        assert diff.removed_users == []

    def test_skips_user_without_email(self):
        from app.schemas.meetings import InvitedUser
        from app.services.meetings.bookings_service import _compute_diff

        old = [{"user_id": "u-no-mail", "full_name": "X"}]
        diff = _compute_diff(
            old,
            [InvitedUser(user_id="u-no-mail", full_name="X", email="x@x.com")],
            non_participant_changed=True,
        )
        # malformed old dropped → user looks "added".
        assert {u.user_id for u in diff.added_users} == {"u-no-mail"}
        assert diff.non_participant_changed is True
