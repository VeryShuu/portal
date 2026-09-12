from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.meetings import MeetingRoom
from app.services.meetings import rooms_service


def _scalars_result(items):
    result = MagicMock()
    scal = MagicMock()
    scal.all.return_value = list(items)
    result.scalars.return_value = scal
    return result


def _scalar_one_or_none_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _first_result(value):
    result = MagicMock()
    result.first.return_value = value
    return result


class TestListActiveRooms:
    async def test_active_only_by_default(self):
        room = MeetingRoom(name="A")
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result([room]))

        rooms = await rooms_service.list_active_rooms(db)

        assert rooms == [room]
        db.execute.assert_awaited_once()

    async def test_include_inactive(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_result([]))

        rooms = await rooms_service.list_active_rooms(db, include_inactive=True)

        assert rooms == []
        db.execute.assert_awaited_once()


class TestGetRoom:
    async def test_found(self):
        room = MeetingRoom(name="A")
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none_result(room))

        assert await rooms_service.get_room(db, uuid.uuid4()) is room

    async def test_missing_returns_none(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))

        assert await rooms_service.get_room(db, uuid.uuid4()) is None


class TestCreateRoom:
    async def test_adds_flushes_and_refreshes(self):
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        payload = MagicMock()
        payload.model_dump.return_value = {"name": "Room 1"}

        room = await rooms_service.create_room(db, payload)

        assert room.name == "Room 1"
        db.add.assert_called_once_with(room)
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once_with(room)
        payload.model_dump.assert_called_once_with(exclude_none=True)


class TestUpdateRoom:
    async def test_applies_changes_and_sets_updated_at(self):
        room = MeetingRoom(name="Old")
        db = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        payload = MagicMock()
        payload.model_dump.return_value = {"name": "New"}

        result = await rooms_service.update_room(db, room, payload)

        assert result is room
        assert room.name == "New"
        assert room.updated_at is not None
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once_with(room)


class TestSoftDeleteRoom:
    async def test_locks_deactivates_and_flushes(self):
        room = MeetingRoom(id=uuid.uuid4(), name="A", is_active=True)
        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()

        await rooms_service.soft_delete_room(db, room)

        assert room.is_active is False
        assert room.updated_at is not None
        db.execute.assert_awaited_once()
        db.flush.assert_awaited_once()


class TestHasFutureBookings:
    async def test_true_when_row_present(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_first_result(("booking-id",)))

        assert await rooms_service.has_future_bookings(db, uuid.uuid4()) is True

    async def test_false_when_no_rows(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_first_result(None))

        assert await rooms_service.has_future_bookings(db, uuid.uuid4()) is False
