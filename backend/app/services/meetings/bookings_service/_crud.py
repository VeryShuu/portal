from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.meetings import MeetingBooking, MeetingBookingRoom
from app.schemas.meetings import BookingCreate, BookingUpdate, InvitedUser

from ._helpers import (
    _compute_diff,
    _get_conflict_details,
    _load_booking,
    _to_utc,
    _verify_rooms_active,
)
from ._types import BookingConflict, BookingDiff

if TYPE_CHECKING:
    from app.models.user import User

logger = get_logger(__name__)


async def create_booking(
    db: AsyncSession,
    *,
    payload: BookingCreate,
    user: User,
    series_id: uuid.UUID | None = None,
    recurrence_rule_str: str | None = None,
) -> MeetingBooking:
    start_time = _to_utc(payload.start_time)
    end_time = _to_utc(payload.end_time)

    await _verify_rooms_active(db, payload.room_ids)

    organizer_name = user.full_name or user.email
    invited_users_data = [u.model_dump() for u in payload.invited_users]

    booking = MeetingBooking(
        title=payload.title,
        description=payload.description,
        organizer_name=organizer_name,
        creator_id=user.id,
        start_time=start_time,
        end_time=end_time,
        invited_users=invited_users_data,
        series_id=series_id,
        recurrence_rule=recurrence_rule_str,
        update_count=0,
    )
    pre_conflicts = await _get_conflict_details(
        db, payload.room_ids, start_time, end_time
    )
    if pre_conflicts:
        logger.info("meetings.booking.conflict", reason="pre_check")
        raise BookingConflict(pre_conflicts)

    db.add(booking)
    await db.flush()

    for room_id in payload.room_ids:
        br = MeetingBookingRoom(
            booking_id=booking.id,
            room_id=room_id,
            start_time=start_time,
            end_time=end_time,
        )
        db.add(br)

    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        with contextlib.suppress(Exception):
            db.expunge(booking)
        logger.info("meetings.booking.conflict", error=str(exc))
        raise BookingConflict([]) from exc

    booking_id = booking.id
    loaded = await _load_booking(db, booking_id)
    if loaded is None:
        raise RuntimeError(f"booking disappeared after flush: {booking_id}")
    return loaded


async def update_booking(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    payload: BookingUpdate,
    user: User,
) -> tuple[MeetingBooking, BookingDiff]:
    booking = await _load_booking(db, booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if booking.creator_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    # NOTE: caller is expected to route apply_to == "series" with a
    # populated series_id to update_series() in series_service. This
    # branch handles the single instance edit (apply_to == "this").

    old_invited = list(booking.invited_users or [])
    new_invited = payload.invited_users if payload.invited_users is not None else [
        InvitedUser(**u) for u in old_invited
    ]

    non_participant_changed = any([
        payload.title is not None and payload.title != booking.title,
        payload.description is not None and payload.description != booking.description,
        payload.start_time is not None,
        payload.end_time is not None,
        payload.room_ids is not None,
    ])

    diff = _compute_diff(old_invited, new_invited, non_participant_changed)

    if payload.title is not None:
        booking.title = payload.title
    if payload.description is not None:
        booking.description = payload.description
    if payload.invited_users is not None:
        booking.invited_users = [u.model_dump() for u in new_invited]

    time_or_rooms_changed = (
        payload.start_time is not None
        or payload.end_time is not None
        or payload.room_ids is not None
    )

    new_start = (
        _to_utc(payload.start_time) if payload.start_time is not None else booking.start_time
    )
    new_end = _to_utc(payload.end_time) if payload.end_time is not None else booking.end_time
    new_room_ids = (
        payload.room_ids
        if payload.room_ids is not None
        else [br.room_id for br in booking.rooms]
    )

    if new_end <= new_start:
        raise HTTPException(
            status_code=422,
            detail="end_time must be after start_time",
        )

    if time_or_rooms_changed:
        await _verify_rooms_active(db, new_room_ids)

        pre_conflicts = await _get_conflict_details(
            db, new_room_ids, new_start, new_end, exclude_booking_id=booking_id
        )
        if pre_conflicts:
            logger.info("meetings.booking.conflict", reason="pre_check_update")
            raise BookingConflict(pre_conflicts)

        await db.execute(
            delete(MeetingBookingRoom).where(MeetingBookingRoom.booking_id == booking.id)
        )
        booking.start_time = new_start
        booking.end_time = new_end

        for room_id in new_room_ids:
            br = MeetingBookingRoom(
                booking_id=booking.id,
                room_id=room_id,
                start_time=new_start,
                end_time=new_end,
            )
            db.add(br)

    if payload.apply_to == "this" and booking.series_id is not None:
        from app.core.system_config import load_system_settings

        raw_url = getattr(load_system_settings(), "portal_base_url", "portal.company.local")
        from urllib.parse import urlparse

        parsed = urlparse(raw_url if "://" in raw_url else f"//{raw_url}")
        company_domain = parsed.hostname or raw_url
        diff.old_series_uid = f"series-{booking.series_id}@{company_domain}"
        booking.series_id = None
        booking.recurrence_rule = None

    if non_participant_changed:
        booking.update_count = (booking.update_count or 0) + 1
    booking.updated_at = datetime.now(UTC)

    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        with contextlib.suppress(Exception):
            db.expunge(booking)
        raise BookingConflict([]) from exc

    loaded = await _load_booking(db, booking_id)
    if loaded is None:
        raise RuntimeError(f"booking disappeared after flush: {booking_id}")
    return loaded, diff


async def delete_booking(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    user: User,
) -> MeetingBooking:
    booking = await _load_booking(db, booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if booking.creator_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    snapshot = booking
    await db.delete(booking)
    await db.flush()
    return snapshot
