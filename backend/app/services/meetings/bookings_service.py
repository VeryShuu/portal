from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.meetings import MeetingBooking, MeetingBookingRoom, MeetingRoom
from app.schemas.meetings import BookingCreate, BookingUpdate, InvitedUser

if TYPE_CHECKING:
    from app.models.user import User

logger = get_logger(__name__)

MY_BOOKINGS_LIMIT_MAX = 50


@dataclass
class ConflictInfo:
    room_name: str
    booking_title: str
    start: datetime
    end: datetime


class BookingConflict(Exception):  # noqa: N818
    def __init__(self, conflicts: list[ConflictInfo]) -> None:
        super().__init__("Booking conflict")
        self.conflicts = conflicts


@dataclass
class BookingDiff:
    added_users: list[InvitedUser] = field(default_factory=list)
    removed_users: list[InvitedUser] = field(default_factory=list)
    unchanged_users: list[InvitedUser] = field(default_factory=list)
    non_participant_changed: bool = False
    old_series_uid: str | None = None


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _date_range(d: date, tz_name: str = "UTC") -> tuple[datetime, datetime]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz).astimezone(UTC)
    end = datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=tz).astimezone(UTC)
    return start, end


async def _load_booking(db: AsyncSession, booking_id: uuid.UUID) -> MeetingBooking | None:
    result = await db.execute(
        select(MeetingBooking)
        .where(MeetingBooking.id == booking_id)
        .options(
            selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room)
        )
    )
    return result.scalar_one_or_none()


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


async def _get_conflict_details(
    db: AsyncSession,
    room_ids: list[uuid.UUID],
    start_time: datetime,
    end_time: datetime,
    exclude_booking_id: uuid.UUID | None = None,
) -> list[ConflictInfo]:
    stmt = (
        select(MeetingBookingRoom, MeetingBooking, MeetingRoom)
        .join(MeetingBooking, MeetingBookingRoom.booking_id == MeetingBooking.id)
        .join(MeetingRoom, MeetingBookingRoom.room_id == MeetingRoom.id)
        .where(
            MeetingBookingRoom.room_id.in_(room_ids),
            MeetingBookingRoom.start_time < end_time,
            MeetingBookingRoom.end_time > start_time,
        )
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(MeetingBookingRoom.booking_id != exclude_booking_id)

    result = await db.execute(stmt)
    rows = result.all()

    conflicts: list[ConflictInfo] = []
    for br, booking, room in rows:
        conflicts.append(
            ConflictInfo(
                room_name=room.name,
                booking_title=booking.title,
                start=br.start_time,
                end=br.end_time,
            )
        )
    return conflicts


async def _verify_rooms_active(
    db: AsyncSession, room_ids: list[uuid.UUID]
) -> list[MeetingRoom]:
    result = await db.execute(
        select(MeetingRoom).where(
            MeetingRoom.id.in_(room_ids),
            MeetingRoom.is_active.is_(True),
        )
    )
    rooms = list(result.scalars().all())
    found_ids = {r.id for r in rooms}
    missing = [rid for rid in room_ids if rid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rooms not found or inactive: {[str(m) for m in missing]}",
        )
    return rooms


def _compute_diff(
    old_users: list[dict],
    new_users: list[InvitedUser],
    non_participant_changed: bool,
) -> BookingDiff:
    valid_old: list[dict] = []
    for u in old_users:
        if not u.get("user_id") or not u.get("email"):
            logger.warning("meetings.diff.malformed_user", entry=u)
            continue
        valid_old.append(u)

    old_ids = {u["user_id"] for u in valid_old}
    new_ids = {u.user_id for u in new_users}

    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids
    unchanged_ids = old_ids & new_ids

    old_by_id = {u["user_id"]: u for u in valid_old}
    new_by_id = {u.user_id: u for u in new_users}

    return BookingDiff(
        added_users=[new_by_id[uid] for uid in added_ids if uid in new_by_id],
        removed_users=[
            InvitedUser(
                user_id=old_by_id[uid]["user_id"],
                full_name=old_by_id[uid].get("full_name", ""),
                email=old_by_id[uid]["email"],
            )
            for uid in removed_ids
            if uid in old_by_id
        ],
        unchanged_users=[new_by_id[uid] for uid in unchanged_ids if uid in new_by_id],
        non_participant_changed=non_participant_changed,
    )


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
        conflicts = await _get_conflict_details(
            db, payload.room_ids, start_time, end_time
        )
        raise BookingConflict(conflicts) from exc

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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_time must be after start_time",
        )

    if time_or_rooms_changed:
        await _verify_rooms_active(db, new_room_ids)

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
        conflicts = await _get_conflict_details(
            db, new_room_ids, new_start, new_end, exclude_booking_id=booking_id
        )
        raise BookingConflict(conflicts) from exc

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
