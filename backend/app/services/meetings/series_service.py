from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.meetings import MeetingBooking, MeetingBookingRoom
from app.schemas.meetings import BookingCreate, InvitedUser, SeriesUpdate
from app.services.meetings.bookings_service import (
    BookingConflict,
    BookingDiff,
    _compute_diff,
    _get_conflict_details,
    _to_utc,
    _verify_rooms_active,
)
from app.services.meetings.recurrence import (
    build_rrule_string,
    expand_recurrence,
    parse_rrule_string,
)

if TYPE_CHECKING:
    from app.models.user import User

logger = get_logger(__name__)


async def _load_bookings_bulk(
    db: AsyncSession, booking_ids: list[uuid.UUID]
) -> list[MeetingBooking]:
    if not booking_ids:
        return []
    result = await db.execute(
        select(MeetingBooking)
        .where(MeetingBooking.id.in_(booking_ids))
        .options(selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room))
        .order_by(MeetingBooking.start_time)
    )
    return list(result.scalars().unique().all())


async def create_booking_series(
    db: AsyncSession,
    *,
    payload: BookingCreate,
    user: User,
) -> list[MeetingBooking]:
    assert payload.recurrence is not None

    start_time = _to_utc(payload.start_time)
    end_time = _to_utc(payload.end_time)

    await _verify_rooms_active(db, payload.room_ids)

    instances = expand_recurrence(start_time, end_time, payload.recurrence, tz="UTC")
    if not instances:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Recurrence rule produces no instances",
        )

    series_id = uuid.uuid4()
    rrule_str = build_rrule_string(payload.recurrence, start_time)
    organizer_name = user.full_name or user.email
    invited_users_data = [u.model_dump() for u in payload.invited_users]

    booking_ids: list[uuid.UUID] = []

    for idx, (inst_start, inst_end) in enumerate(instances):
        booking = MeetingBooking(
            title=payload.title,
            description=payload.description,
            organizer_name=organizer_name,
            creator_id=user.id,
            start_time=inst_start,
            end_time=inst_end,
            invited_users=invited_users_data,
            series_id=series_id,
            # Strategy A: keep RRULE on the canonical (first) instance only.
            recurrence_rule=rrule_str if idx == 0 else None,
            update_count=0,
        )
        db.add(booking)
        await db.flush()

        for room_id in payload.room_ids:
            br = MeetingBookingRoom(
                booking_id=booking.id,
                room_id=room_id,
                start_time=inst_start,
                end_time=inst_end,
            )
            db.add(br)

        try:
            async with db.begin_nested():
                await db.flush()
        except IntegrityError as exc:
            logger.info("meetings.series.conflict", idx=idx, error=str(exc))
            conflicts = await _get_conflict_details(
                db, payload.room_ids, inst_start, inst_end
            )
            raise BookingConflict(conflicts) from exc

        booking_ids.append(booking.id)

    # Reload all bookings in a single query with rooms eagerly loaded.
    bookings = await _load_bookings_bulk(db, booking_ids)
    return bookings


async def get_series_count(db: AsyncSession, series_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).where(MeetingBooking.series_id == series_id)
    )
    return result.scalar_one()


async def update_series(
    db: AsyncSession,
    *,
    series_id: uuid.UUID,
    payload: SeriesUpdate,
    user: User,
) -> tuple[list[MeetingBooking], BookingDiff]:
    result = await db.execute(
        select(MeetingBooking)
        .where(MeetingBooking.series_id == series_id)
        .options(selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room))
        .order_by(MeetingBooking.start_time)
    )
    bookings = list(result.scalars().all())

    if not bookings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")

    first = bookings[0]
    if first.creator_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    old_invited = list(first.invited_users or [])
    new_invited = (
        payload.invited_users
        if payload.invited_users is not None
        else [InvitedUser(**u) for u in old_invited]
    )

    non_participant_changed = any([
        payload.title is not None and payload.title != first.title,
        payload.description is not None and payload.description != first.description,
        payload.start_time is not None,
        payload.end_time is not None,
        payload.room_ids is not None,
    ])
    diff = _compute_diff(old_invited, new_invited, non_participant_changed)

    # Compute the delta relative to the first instance, so the rest of the
    # series shifts by the same amount.
    start_delta: timedelta | None = None
    end_delta: timedelta | None = None
    if payload.start_time is not None:
        new_first_start = _to_utc(payload.start_time)
        start_delta = new_first_start - first.start_time
    if payload.end_time is not None:
        new_first_end = _to_utc(payload.end_time)
        end_delta = new_first_end - first.end_time

    if payload.room_ids is not None:
        await _verify_rooms_active(db, payload.room_ids)

    now_utc = datetime.now(UTC)
    invited_data = [u.model_dump() for u in new_invited]

    room_ids_snapshot: dict[uuid.UUID, list[uuid.UUID]] = {
        b.id: [br.room_id for br in b.rooms] for b in bookings
    }

    # If start_time changed, recompute RRULE on the canonical first booking so
    # BYDAY/BYMONTHDAY stay consistent with the new DTSTART.
    if start_delta is not None and first.recurrence_rule:
        parsed = parse_rrule_string(first.recurrence_rule)
        if parsed is not None:
            new_first_start = first.start_time + start_delta
            first.recurrence_rule = build_rrule_string(parsed, new_first_start)

    for booking in bookings:
        if payload.title is not None:
            booking.title = payload.title
        if payload.description is not None:
            booking.description = payload.description
        if payload.invited_users is not None:
            booking.invited_users = invited_data

        new_start = booking.start_time + start_delta if start_delta else booking.start_time
        new_end = booking.end_time + end_delta if end_delta else booking.end_time

        time_changed = start_delta is not None or end_delta is not None
        rooms_changed = payload.room_ids is not None

        if time_changed or rooms_changed:
            await db.execute(
                delete(MeetingBookingRoom).where(
                    MeetingBookingRoom.booking_id == booking.id
                )
            )
            booking.start_time = new_start
            booking.end_time = new_end
            new_room_ids = (
                payload.room_ids
                if payload.room_ids is not None
                else room_ids_snapshot.get(booking.id, [])
            )
            for room_id in new_room_ids:
                db.add(
                    MeetingBookingRoom(
                        booking_id=booking.id,
                        room_id=room_id,
                        start_time=new_start,
                        end_time=new_end,
                    )
                )

        if non_participant_changed:
            booking.update_count = (booking.update_count or 0) + 1
        booking.updated_at = now_utc

    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        for booking in bookings:
            with contextlib.suppress(Exception):
                db.expunge(booking)
        # Provide best-effort conflict details for the first instance.
        first_b = bookings[0]
        ref_start = (first_b.start_time + start_delta) if start_delta else first_b.start_time
        ref_end = (first_b.end_time + end_delta) if end_delta else first_b.end_time
        ref_rooms = payload.room_ids or [br.room_id for br in first_b.rooms]
        conflicts = await _get_conflict_details(db, ref_rooms, ref_start, ref_end)
        raise BookingConflict(conflicts) from exc

    # Reload with rooms in a single query, preserving start_time order.
    reloaded = await _load_bookings_bulk(db, [b.id for b in bookings])
    return reloaded, diff


async def delete_series(
    db: AsyncSession,
    *,
    series_id: uuid.UUID,
    user: User,
) -> list[MeetingBooking]:
    result = await db.execute(
        select(MeetingBooking)
        .where(MeetingBooking.series_id == series_id)
        .options(selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room))
    )
    bookings = list(result.scalars().all())

    if not bookings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")

    first = bookings[0]
    if first.creator_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    # Snapshot before bulk delete so the caller can build cancel notifications.
    snapshots = list(bookings)

    await db.execute(
        delete(MeetingBooking).where(MeetingBooking.series_id == series_id)
    )
    await db.flush()
    return snapshots
