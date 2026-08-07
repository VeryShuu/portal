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
    invited_users_to_jsonb,
)
from ._types import BookingConflict, BookingDiff

if TYPE_CHECKING:
    from app.models.user import User

logger = get_logger(__name__)


def _ensure_booking_editable(booking: MeetingBooking, user: User) -> None:
    if booking.creator_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )


async def _flush_or_conflict(
    db: AsyncSession, booking: MeetingBooking, *, log_conflict: bool = False
) -> None:
    """Flush in a savepoint; map a uniqueness IntegrityError to BookingConflict."""
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        with contextlib.suppress(Exception):
            db.expunge(booking)
        if log_conflict:
            logger.info("meetings.booking.conflict", error=str(exc))
        raise BookingConflict([]) from exc


def _resolve_new_invited(payload: BookingUpdate, old_invited: list[dict]) -> list[InvitedUser]:
    if payload.invited_users is not None:
        return payload.invited_users
    return [InvitedUser(**u) for u in old_invited]


def _is_non_participant_change(payload: BookingUpdate, booking: MeetingBooking) -> bool:
    return any(
        [
            payload.title is not None and payload.title != booking.title,
            payload.description is not None and payload.description != booking.description,
            payload.start_time is not None,
            payload.end_time is not None,
            payload.room_ids is not None,
        ]
    )


def _resolve_new_schedule(
    payload: BookingUpdate, booking: MeetingBooking
) -> tuple[datetime, datetime, list[uuid.UUID]]:
    new_start = (
        _to_utc(payload.start_time) if payload.start_time is not None else booking.start_time
    )
    new_end = _to_utc(payload.end_time) if payload.end_time is not None else booking.end_time
    new_room_ids = (
        payload.room_ids if payload.room_ids is not None else [br.room_id for br in booking.rooms]
    )
    return new_start, new_end, new_room_ids


async def _rebuild_booking_rooms(
    db: AsyncSession,
    booking: MeetingBooking,
    *,
    new_start: datetime,
    new_end: datetime,
    new_room_ids: list[uuid.UUID],
) -> None:
    await db.execute(delete(MeetingBookingRoom).where(MeetingBookingRoom.booking_id == booking.id))
    booking.start_time = new_start
    booking.end_time = new_end
    for room_id in new_room_ids:
        db.add(
            MeetingBookingRoom(
                booking_id=booking.id,
                room_id=room_id,
                start_time=new_start,
                end_time=new_end,
            )
        )
    # The bulk DELETE above bypasses the ORM, so the in-memory ``booking.rooms``
    # collection (identity map) keeps the OLD room rows. Expire it so the next
    # access — including the post-update reload and the iCal/HTML builders that
    # run before commit — refetches the freshly added rooms. Without this the
    # calendar/email notification carries the previous room (see regression test
    # test_update_room_change_reflected_in_rooms_and_ical).
    db.expire(booking, ["rooms"])


async def _apply_schedule_change(
    db: AsyncSession,
    booking: MeetingBooking,
    *,
    booking_id: uuid.UUID,
    new_start: datetime,
    new_end: datetime,
    new_room_ids: list[uuid.UUID],
) -> None:
    """Validate rooms, pre-check conflicts and rebuild the room rows."""
    await _verify_rooms_active(db, new_room_ids)

    pre_conflicts = await _get_conflict_details(
        db, new_room_ids, new_start, new_end, exclude_booking_id=booking_id
    )
    if pre_conflicts:
        logger.info("meetings.booking.conflict", reason="pre_check_update")
        raise BookingConflict(pre_conflicts)

    await _rebuild_booking_rooms(
        db, booking, new_start=new_start, new_end=new_end, new_room_ids=new_room_ids
    )


def _detach_from_series(booking: MeetingBooking, diff: BookingDiff) -> None:
    """Split a single instance off its series, recording the old series UID."""
    from urllib.parse import urlparse

    from app.core.system_config import load_system_settings

    raw_url = getattr(load_system_settings(), "portal_base_url", "portal.company.local")
    parsed = urlparse(raw_url if "://" in raw_url else f"//{raw_url}")
    company_domain = parsed.hostname or raw_url
    diff.old_series_uid = f"series-{booking.series_id}@{company_domain}"
    booking.series_id = None
    booking.recurrence_rule = None


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
    invited_users_data = invited_users_to_jsonb(payload.invited_users)

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
    pre_conflicts = await _get_conflict_details(db, payload.room_ids, start_time, end_time)
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

    await _flush_or_conflict(db, booking, log_conflict=True)

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

    _ensure_booking_editable(booking, user)

    # NOTE: caller is expected to route apply_to == "series" with a
    # populated series_id to update_series() in series_service. This
    # branch handles the single instance edit (apply_to == "this").

    old_invited = list(booking.invited_users or [])
    new_invited = _resolve_new_invited(payload, old_invited)
    non_participant_changed = _is_non_participant_change(payload, booking)
    diff = _compute_diff(old_invited, new_invited, non_participant_changed)

    if payload.title is not None:
        booking.title = payload.title
    if payload.description is not None:
        booking.description = payload.description
    if payload.invited_users is not None:
        booking.invited_users = invited_users_to_jsonb(new_invited)

    new_start, new_end, new_room_ids = _resolve_new_schedule(payload, booking)
    if new_end <= new_start:
        raise HTTPException(
            status_code=422,
            detail="end_time must be after start_time",
        )

    time_or_rooms_changed = (
        payload.start_time is not None
        or payload.end_time is not None
        or payload.room_ids is not None
    )
    if time_or_rooms_changed:
        await _apply_schedule_change(
            db,
            booking,
            booking_id=booking_id,
            new_start=new_start,
            new_end=new_end,
            new_room_ids=new_room_ids,
        )

    if payload.apply_to == "this" and booking.series_id is not None:
        _detach_from_series(booking, diff)

    if non_participant_changed:
        booking.update_count = (booking.update_count or 0) + 1
    booking.updated_at = datetime.now(UTC)

    await _flush_or_conflict(db, booking)

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

    _ensure_booking_editable(booking, user)

    snapshot = booking
    await db.delete(booking)
    await db.flush()
    return snapshot
