"""TST-06: SEQUENCE (update_count) must not increase when only invited_users change.

RFC 5545: SEQUENCE is bumped only on substantive changes to the event itself
(time, title, description, location). Adding/removing participants must not
trigger a SEQUENCE bump.
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

    return await create_room(real_db_session, RoomCreate(name=f"Seq-{uuid.uuid4().hex[:6]}"))


async def test_sequence_unchanged_when_only_invited_users_change(real_db_session, real_user, room):
    from app.schemas.meetings import BookingCreate, BookingUpdate, InvitedUser
    from app.services.meetings.bookings_service import create_booking, update_booking

    start, end = _slot()
    booking = await create_booking(
        real_db_session,
        payload=BookingCreate(
            title="x",
            start_time=start,
            end_time=end,
            room_ids=[room.id],
            invited_users=[InvitedUser(user_id="u1", full_name="A", email="a@x.com")],
        ),
        user=real_user,
    )
    assert booking.update_count == 0

    updated, diff = await update_booking(
        real_db_session,
        booking_id=booking.id,
        payload=BookingUpdate(
            invited_users=[
                InvitedUser(user_id="u1", full_name="A", email="a@x.com"),
                InvitedUser(user_id="u2", full_name="B", email="b@x.com"),
            ]
        ),
        user=real_user,
    )
    assert updated.update_count == 0, "SEQUENCE must NOT bump on participant-only change"
    assert diff.non_participant_changed is False


async def test_sequence_bumped_when_start_time_changes(real_db_session, real_user, room):
    from app.schemas.meetings import BookingCreate, BookingUpdate
    from app.services.meetings.bookings_service import create_booking, update_booking

    start, end = _slot()
    booking = await create_booking(
        real_db_session,
        payload=BookingCreate(title="x", start_time=start, end_time=end, room_ids=[room.id]),
        user=real_user,
    )
    new_start = start + timedelta(hours=4)
    new_end = end + timedelta(hours=4)
    updated, diff = await update_booking(
        real_db_session,
        booking_id=booking.id,
        payload=BookingUpdate(start_time=new_start, end_time=new_end),
        user=real_user,
    )
    assert updated.update_count == 1
    assert diff.non_participant_changed is True
