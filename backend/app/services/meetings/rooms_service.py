from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meetings import MeetingBookingRoom, MeetingRoom
from app.schemas.meetings import RoomCreate, RoomUpdate


async def list_active_rooms(
    db: AsyncSession,
    include_inactive: bool = False,
) -> list[MeetingRoom]:
    stmt = select(MeetingRoom)
    if not include_inactive:
        stmt = stmt.where(MeetingRoom.is_active.is_(True))
    stmt = stmt.order_by(MeetingRoom.sort_order, MeetingRoom.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_room(db: AsyncSession, room_id: uuid.UUID) -> MeetingRoom | None:
    result = await db.execute(select(MeetingRoom).where(MeetingRoom.id == room_id))
    return result.scalar_one_or_none()


async def create_room(db: AsyncSession, payload: RoomCreate) -> MeetingRoom:
    room = MeetingRoom(**payload.model_dump(exclude_none=True))
    db.add(room)
    await db.flush()
    await db.refresh(room)
    return room


async def update_room(
    db: AsyncSession, room: MeetingRoom, payload: RoomUpdate
) -> MeetingRoom:
    changes = payload.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(room, field, value)
    room.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(room)
    return room


async def soft_delete_room(db: AsyncSession, room: MeetingRoom) -> None:
    # Acquire row-level lock so concurrent bookings cannot be inserted while
    # we deactivate the room.
    await db.execute(
        select(MeetingRoom.id).where(MeetingRoom.id == room.id).with_for_update()
    )
    room.is_active = False
    room.updated_at = datetime.now(UTC)
    await db.flush()


async def has_future_bookings(db: AsyncSession, room_id: uuid.UUID) -> bool:
    now = datetime.now(UTC)
    result = await db.execute(
        select(MeetingBookingRoom.booking_id).where(
            MeetingBookingRoom.room_id == room_id,
            MeetingBookingRoom.end_time > now,
        )
    )
    return result.first() is not None
