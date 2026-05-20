"""TST-01: BookingConflict must use SAVEPOINT, not rollback the outer session.

A conflicting INSERT inside create/update must only unwind the nested
transaction. Other rows previously added in the same outer session must
survive (e.g. audit rows committed earlier in the request).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


def _slot(offset_hours: int = 30) -> tuple[datetime, datetime]:
    base = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=offset_hours)
    return base, base + timedelta(hours=1)


@pytest_asyncio.fixture
async def room(real_db_session):
    from app.schemas.meetings import RoomCreate
    from app.services.meetings.rooms_service import create_room

    return await create_room(
        real_db_session, RoomCreate(name=f"SP-{uuid.uuid4().hex[:6]}")
    )


async def test_conflict_does_not_unwind_unrelated_booking_in_same_session(
    real_db_session, real_user, room
):
    """A pre-existing booking must remain after a conflicting INSERT fails."""
    from app.schemas.meetings import BookingCreate
    from app.services.meetings.bookings_service import (
        BookingConflict,
        create_booking,
        list_bookings,
    )

    start, end = _slot()
    first = await create_booking(
        real_db_session,
        payload=BookingCreate(
            title="Persist-me",
            start_time=start,
            end_time=end,
            room_ids=[room.id],
        ),
        user=real_user,
    )
    await real_db_session.flush()

    with pytest.raises(BookingConflict):
        await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="Conflicting",
                start_time=start + timedelta(minutes=15),
                end_time=end + timedelta(minutes=15),
                room_ids=[room.id],
            ),
            user=real_user,
        )

    # The first booking must still be reachable on the same session.
    rows = await list_bookings(
        real_db_session,
        date=start.date(),
        room_id=room.id,
        limit=10,
    )
    ids = {b.id for b in rows}
    assert first.id in ids, "outer transaction must not have been rolled back"
