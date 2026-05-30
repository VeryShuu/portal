from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.meetings import MeetingBooking, MeetingBookingRoom

from ._helpers import _date_range, _load_booking
from ._types import MY_BOOKINGS_LIMIT_MAX


async def list_bookings(
    db: AsyncSession,
    *,
    date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    room_id: uuid.UUID | None = None,
    creator_id: uuid.UUID | None = None,
    limit: int = 500,
    offset: int = 0,
    tz: str | None = None,
) -> list[MeetingBooking]:
    if tz is None:
        from app.core.system_config import load_system_settings

        tz = load_system_settings().timezone

    stmt = select(MeetingBooking).options(
        selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room)
    )

    if date is not None:
        range_start, range_end = _date_range(date, tz)
        stmt = stmt.where(
            MeetingBooking.start_time >= range_start,
            MeetingBooking.start_time <= range_end,
        )
    elif start_date is not None or end_date is not None:
        if start_date is not None and end_date is not None:
            # Overlap: include any booking that intersects the requested window.
            range_start = _date_range(start_date, tz)[0]
            range_end = _date_range(end_date, tz)[1]
            stmt = stmt.where(
                MeetingBooking.start_time <= range_end,
                MeetingBooking.end_time >= range_start,
            )
        elif start_date is not None:
            stmt = stmt.where(MeetingBooking.end_time >= _date_range(start_date, tz)[0])
        elif end_date is not None:
            stmt = stmt.where(MeetingBooking.start_time <= _date_range(end_date, tz)[1])

    if room_id is not None:
        stmt = stmt.join(MeetingBookingRoom).where(MeetingBookingRoom.room_id == room_id)

    if creator_id is not None:
        stmt = stmt.where(MeetingBooking.creator_id == creator_id)

    stmt = stmt.order_by(MeetingBooking.start_time).limit(min(limit, 500)).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


async def list_my_bookings(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    start_date: date | None = None,
    limit: int = 5,
) -> list[MeetingBooking]:
    if start_date is None:
        start_date = datetime.now(UTC).date()

    stmt = (
        select(MeetingBooking)
        .options(selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room))
        .where(
            MeetingBooking.creator_id == user_id,
            MeetingBooking.start_time >= _date_range(start_date)[0],
        )
        .order_by(MeetingBooking.start_time)
        .limit(min(limit, MY_BOOKINGS_LIMIT_MAX))
    )
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


async def get_booking(db: AsyncSession, booking_id: uuid.UUID) -> MeetingBooking | None:
    return await _load_booking(db, booking_id)
