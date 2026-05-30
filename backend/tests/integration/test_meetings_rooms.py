"""Integration tests for meetings rooms service.

Exercises CRUD, future-booking guard, and is_active filter against a real
PostgreSQL instance via real_db_session (SAVEPOINT-isolated).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def room_payload():
    from app.schemas.meetings import RoomCreate

    def _make(name: str = "Zoom Gold", **kw):
        return RoomCreate(name=name, **kw)

    return _make


class TestRoomsCRUD:
    async def test_create_and_get_room(self, real_db_session, room_payload):
        from app.services.meetings.rooms_service import create_room, get_room

        room = await create_room(real_db_session, room_payload(name=f"R-{uuid.uuid4().hex[:6]}"))
        assert room.id is not None
        assert room.is_active is True
        assert room.timezone == "Europe/Moscow"

        loaded = await get_room(real_db_session, room.id)
        assert loaded is not None
        assert loaded.id == room.id

    async def test_list_active_rooms_excludes_inactive(self, real_db_session, room_payload):
        from app.services.meetings.rooms_service import (
            create_room,
            list_active_rooms,
            soft_delete_room,
        )

        active = await create_room(real_db_session, room_payload(name=f"A-{uuid.uuid4().hex[:6]}"))
        gone = await create_room(real_db_session, room_payload(name=f"D-{uuid.uuid4().hex[:6]}"))
        await soft_delete_room(real_db_session, gone)

        active_only = await list_active_rooms(real_db_session)
        ids = {r.id for r in active_only}
        assert active.id in ids
        assert gone.id not in ids

        with_all = await list_active_rooms(real_db_session, include_inactive=True)
        ids_all = {r.id for r in with_all}
        assert gone.id in ids_all

    async def test_update_room_changes_fields(self, real_db_session, room_payload):
        from app.schemas.meetings import RoomUpdate
        from app.services.meetings.rooms_service import create_room, update_room

        room = await create_room(real_db_session, room_payload(name=f"R-{uuid.uuid4().hex[:6]}"))
        updated = await update_room(
            real_db_session,
            room,
            RoomUpdate(name="Renamed", timezone="Europe/Samara", link="https://x"),
        )
        assert updated.name == "Renamed"
        assert updated.timezone == "Europe/Samara"
        assert updated.link == "https://x"

    async def test_soft_delete_sets_inactive(self, real_db_session, room_payload):
        from app.services.meetings.rooms_service import create_room, soft_delete_room

        room = await create_room(real_db_session, room_payload(name=f"R-{uuid.uuid4().hex[:6]}"))
        await soft_delete_room(real_db_session, room)
        assert room.is_active is False

    async def test_create_room_persists_email(self, real_db_session, room_payload):
        from app.services.meetings.rooms_service import create_room, get_room

        room = await create_room(
            real_db_session,
            room_payload(name=f"E-{uuid.uuid4().hex[:6]}", email="room@x.com"),
        )
        assert room.email == "room@x.com"

        loaded = await get_room(real_db_session, room.id)
        assert loaded is not None
        assert loaded.email == "room@x.com"

    async def test_has_future_bookings_detects_active_booking(
        self, real_db_session, real_user, room_payload
    ):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import create_booking
        from app.services.meetings.rooms_service import create_room, has_future_bookings

        room = await create_room(real_db_session, room_payload(name=f"R-{uuid.uuid4().hex[:6]}"))
        assert await has_future_bookings(real_db_session, room.id) is False

        start = datetime.now(UTC) + timedelta(days=1)
        end = start + timedelta(hours=1)
        await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="Future", start_time=start, end_time=end, room_ids=[room.id]
            ),
            user=real_user,
        )

        assert await has_future_bookings(real_db_session, room.id) is True
