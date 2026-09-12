from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AdminDep, CurrentUser, DbDep
from app.api.meetings import MeetingsGuard
from app.core.logging import get_logger
from app.schemas.meetings import RoomCreate, RoomOut, RoomUpdate
from app.services.meetings.audit import (
    ROOM_CREATED,
    ROOM_DELETED,
    ROOM_UPDATED,
    push_meetings_audit,
)
from app.services.meetings.rooms_service import (
    create_room,
    get_room,
    has_future_bookings,
    list_active_rooms,
    soft_delete_room,
    update_room,
)

router = APIRouter(
    prefix="/meetings/rooms",
    tags=["meetings"],
    dependencies=[MeetingsGuard],
)
logger = get_logger(__name__)


@router.get("", response_model=list[RoomOut])
async def list_rooms(
    user: CurrentUser,
    db: DbDep,
    include_inactive: bool = False,
) -> list[RoomOut]:
    rooms = await list_active_rooms(db, include_inactive=include_inactive)
    return [RoomOut.model_validate(r) for r in rooms]


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
async def create_room_endpoint(
    payload: RoomCreate,
    admin: AdminDep,
    db: DbDep,
    request: Request,
) -> RoomOut:
    room = await create_room(db, payload)
    await db.commit()
    await db.refresh(room)
    await push_meetings_audit(
        action=ROOM_CREATED,
        user=admin,
        request=request,
        resource_type="room",
        resource_id=room.id,
        resource_title=room.name,
    )
    logger.info("meetings.room.created", room_id=str(room.id), admin=str(admin.id))
    return cast(RoomOut, RoomOut.model_validate(room))


@router.get("/{room_id}", response_model=RoomOut)
async def get_room_endpoint(
    room_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> RoomOut:
    room = await get_room(db, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return cast(RoomOut, RoomOut.model_validate(room))


@router.put("/{room_id}", response_model=RoomOut)
async def update_room_endpoint(
    room_id: uuid.UUID,
    payload: RoomUpdate,
    admin: AdminDep,
    db: DbDep,
    request: Request,
) -> RoomOut:
    room = await get_room(db, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    room = await update_room(db, room, payload)
    await db.commit()
    await db.refresh(room)
    await push_meetings_audit(
        action=ROOM_UPDATED,
        user=admin,
        request=request,
        resource_type="room",
        resource_id=room.id,
        resource_title=room.name,
        details={"fields": sorted(payload.model_dump(exclude_none=True).keys())},
    )
    logger.info("meetings.room.updated", room_id=str(room.id), admin=str(admin.id))
    return cast(RoomOut, RoomOut.model_validate(room))


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room_endpoint(
    room_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
    request: Request,
) -> None:
    room = await get_room(db, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    if await has_future_bookings(db, room_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="У комнаты есть будущие бронирования",
        )
    await soft_delete_room(db, room)
    await db.commit()
    await push_meetings_audit(
        action=ROOM_DELETED,
        user=admin,
        request=request,
        resource_type="room",
        resource_id=room_id,
        resource_title=room.name,
    )
    logger.info("meetings.room.deleted", room_id=str(room_id), admin=str(admin.id))
