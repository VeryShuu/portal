from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


def _make_user(role: str = "user"):
    uid = uuid.uuid4()
    return SimpleNamespace(
        id=uid,
        email="user@test.com",
        full_name="Test User",
        role=role,
    )


def _make_payload(
    title: str = "Test Meeting",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    room_ids: list[uuid.UUID] | None = None,
    invited_users: list | None = None,
    description: str | None = None,
):
    from app.schemas.meetings import BookingCreate

    if start_time is None:
        start_time = datetime(2030, 6, 1, 10, 0, tzinfo=UTC)
    if end_time is None:
        end_time = datetime(2030, 6, 1, 11, 0, tzinfo=UTC)
    if room_ids is None:
        room_ids = [uuid.uuid4()]

    return BookingCreate(
        title=title,
        start_time=start_time,
        end_time=end_time,
        room_ids=room_ids,
        invited_users=invited_users or [],
        description=description,
    )


def _make_booking_orm(
    creator_id: uuid.UUID | None = None,
    series_id: uuid.UUID | None = None,
    title: str = "Test Meeting",
):
    bid = uuid.uuid4()
    if creator_id is None:
        creator_id = uuid.uuid4()
    booking = MagicMock()
    booking.id = bid
    booking.title = title
    booking.description = None
    booking.creator_id = creator_id
    booking.series_id = series_id
    booking.recurrence_rule = None
    booking.start_time = datetime(2030, 6, 1, 10, 0, tzinfo=UTC)
    booking.end_time = datetime(2030, 6, 1, 11, 0, tzinfo=UTC)
    booking.invited_users = []
    booking.rooms = []
    booking.update_count = 0
    return booking


def _make_db_with_booking(booking=None):
    db = AsyncMock()

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = booking

    scalars_result = MagicMock()
    scalars_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    scalars_result.all.return_value = []

    db.execute = AsyncMock(return_value=scalar_result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.expunge = MagicMock()

    begin_nested_ctx = AsyncMock()
    begin_nested_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_nested_ctx.__aexit__ = AsyncMock(return_value=None)
    db.begin_nested = MagicMock(return_value=begin_nested_ctx)

    return db


class TestCreateBooking:
    async def test_create_booking_success(self):
        from app.services.meetings.bookings_service._crud import create_booking

        user = _make_user()
        payload = _make_payload()
        booking = _make_booking_orm(creator_id=user.id)

        db = _make_db_with_booking(booking=booking)

        verify_mock = AsyncMock(return_value=[MagicMock(id=payload.room_ids[0])])
        conflict_mock = AsyncMock(return_value=[])
        load_mock = AsyncMock(return_value=booking)

        with (
            patch("app.services.meetings.bookings_service._crud._verify_rooms_active", verify_mock),
            patch("app.services.meetings.bookings_service._crud._get_conflict_details", conflict_mock),
            patch("app.services.meetings.bookings_service._crud._load_booking", load_mock),
        ):
            result = await create_booking(db, payload=payload, user=user)

        assert result is booking
        db.add.assert_called()
        db.flush.assert_awaited()

    async def test_create_booking_with_conflict_raises(self):
        from app.services.meetings.bookings_service._crud import create_booking
        from app.services.meetings.bookings_service._types import BookingConflict, ConflictInfo

        user = _make_user()
        payload = _make_payload()

        db = _make_db_with_booking()

        conflict = ConflictInfo(
            room_name="Room A",
            booking_title="Other",
            start=datetime(2030, 6, 1, 10, 0, tzinfo=UTC),
            end=datetime(2030, 6, 1, 11, 0, tzinfo=UTC),
        )
        verify_mock = AsyncMock(return_value=[MagicMock(id=payload.room_ids[0])])
        conflict_mock = AsyncMock(return_value=[conflict])
        load_mock = AsyncMock(return_value=None)

        with (
            patch("app.services.meetings.bookings_service._crud._verify_rooms_active", verify_mock),
            patch("app.services.meetings.bookings_service._crud._get_conflict_details", conflict_mock),
            patch("app.services.meetings.bookings_service._crud._load_booking", load_mock),
        ):
            with pytest.raises(BookingConflict):
                await create_booking(db, payload=payload, user=user)

    async def test_create_booking_with_series_id(self):
        from app.services.meetings.bookings_service._crud import create_booking

        user = _make_user()
        series_id = uuid.uuid4()
        payload = _make_payload()
        booking = _make_booking_orm(creator_id=user.id, series_id=series_id)

        db = _make_db_with_booking(booking=booking)

        verify_mock = AsyncMock(return_value=[MagicMock(id=payload.room_ids[0])])
        conflict_mock = AsyncMock(return_value=[])
        load_mock = AsyncMock(return_value=booking)

        with (
            patch("app.services.meetings.bookings_service._crud._verify_rooms_active", verify_mock),
            patch("app.services.meetings.bookings_service._crud._get_conflict_details", conflict_mock),
            patch("app.services.meetings.bookings_service._crud._load_booking", load_mock),
        ):
            result = await create_booking(db, payload=payload, user=user, series_id=series_id)

        assert result is booking

    async def test_create_booking_integrity_error_raises_conflict(self):
        from sqlalchemy.exc import IntegrityError

        from app.services.meetings.bookings_service._crud import create_booking
        from app.services.meetings.bookings_service._types import BookingConflict

        user = _make_user()
        payload = _make_payload()
        booking = _make_booking_orm(creator_id=user.id)

        db = _make_db_with_booking(booking=booking)

        begin_nested_ctx = AsyncMock()
        begin_nested_ctx.__aenter__ = AsyncMock(return_value=None)
        begin_nested_ctx.__aexit__ = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("unique")))
        db.begin_nested = MagicMock(return_value=begin_nested_ctx)

        verify_mock = AsyncMock(return_value=[MagicMock(id=payload.room_ids[0])])
        conflict_mock = AsyncMock(return_value=[])

        with (
            patch("app.services.meetings.bookings_service._crud._verify_rooms_active", verify_mock),
            patch("app.services.meetings.bookings_service._crud._get_conflict_details", conflict_mock),
        ):
            with pytest.raises(BookingConflict):
                await create_booking(db, payload=payload, user=user)

    async def test_create_booking_uses_email_when_no_full_name(self):
        from app.services.meetings.bookings_service._crud import create_booking

        user = _make_user()
        user.full_name = None
        user.email = "fallback@test.com"
        payload = _make_payload()
        booking = _make_booking_orm(creator_id=user.id)

        db = _make_db_with_booking(booking=booking)

        verify_mock = AsyncMock(return_value=[MagicMock(id=payload.room_ids[0])])
        conflict_mock = AsyncMock(return_value=[])
        load_mock = AsyncMock(return_value=booking)

        with (
            patch("app.services.meetings.bookings_service._crud._verify_rooms_active", verify_mock),
            patch("app.services.meetings.bookings_service._crud._get_conflict_details", conflict_mock),
            patch("app.services.meetings.bookings_service._crud._load_booking", load_mock),
        ):
            result = await create_booking(db, payload=payload, user=user)

        assert result is booking


class TestUpdateBooking:
    async def test_update_not_found_raises_404(self):
        from app.schemas.meetings import BookingUpdate
        from app.services.meetings.bookings_service._crud import update_booking

        user = _make_user()
        db = _make_db_with_booking()
        load_mock = AsyncMock(return_value=None)

        with patch("app.services.meetings.bookings_service._crud._load_booking", load_mock):
            with pytest.raises(HTTPException) as exc_info:
                await update_booking(db, booking_id=uuid.uuid4(), payload=BookingUpdate(), user=user)
        assert exc_info.value.status_code == 404

    async def test_update_forbidden_for_non_owner(self):
        from app.schemas.meetings import BookingUpdate
        from app.services.meetings.bookings_service._crud import update_booking

        user = _make_user(role="user")
        booking = _make_booking_orm(creator_id=uuid.uuid4())
        db = _make_db_with_booking(booking=booking)
        load_mock = AsyncMock(return_value=booking)

        with patch("app.services.meetings.bookings_service._crud._load_booking", load_mock):
            with pytest.raises(HTTPException) as exc_info:
                await update_booking(db, booking_id=booking.id, payload=BookingUpdate(), user=user)
        assert exc_info.value.status_code == 403

    async def test_update_admin_can_update_others_booking(self):
        from app.schemas.meetings import BookingUpdate
        from app.services.meetings.bookings_service._crud import update_booking

        admin = _make_user(role="admin")
        booking = _make_booking_orm(creator_id=uuid.uuid4())

        db = _make_db_with_booking(booking=booking)
        load_mock = AsyncMock(return_value=booking)

        begin_nested_ctx = AsyncMock()
        begin_nested_ctx.__aenter__ = AsyncMock(return_value=None)
        begin_nested_ctx.__aexit__ = AsyncMock(return_value=None)
        db.begin_nested = MagicMock(return_value=begin_nested_ctx)

        with patch("app.services.meetings.bookings_service._crud._load_booking", load_mock):
            result_booking, diff = await update_booking(
                db, booking_id=booking.id, payload=BookingUpdate(), user=admin
            )
        assert result_booking is booking

    async def test_update_title_changes_title(self):
        from app.schemas.meetings import BookingUpdate
        from app.services.meetings.bookings_service._crud import update_booking

        user = _make_user()
        booking = _make_booking_orm(creator_id=user.id)
        db = _make_db_with_booking(booking=booking)
        load_mock = AsyncMock(return_value=booking)

        begin_nested_ctx = AsyncMock()
        begin_nested_ctx.__aenter__ = AsyncMock(return_value=None)
        begin_nested_ctx.__aexit__ = AsyncMock(return_value=None)
        db.begin_nested = MagicMock(return_value=begin_nested_ctx)

        payload = BookingUpdate(title="New Title")

        with patch("app.services.meetings.bookings_service._crud._load_booking", load_mock):
            result_booking, diff = await update_booking(
                db, booking_id=booking.id, payload=payload, user=user
            )

        assert booking.title == "New Title"

    async def test_update_end_before_start_raises(self):
        from app.schemas.meetings import BookingUpdate
        from app.services.meetings.bookings_service._crud import update_booking

        user = _make_user()
        booking = _make_booking_orm(creator_id=user.id)
        booking.start_time = datetime(2030, 6, 1, 10, 0, tzinfo=UTC)
        booking.end_time = datetime(2030, 6, 1, 11, 0, tzinfo=UTC)
        booking.rooms = []

        db = _make_db_with_booking(booking=booking)
        load_mock = AsyncMock(return_value=booking)

        payload = BookingUpdate(
            start_time=datetime(2030, 6, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2030, 6, 1, 11, 0, tzinfo=UTC),
        )
        payload.start_time = datetime(2030, 6, 1, 12, 0, tzinfo=UTC)
        payload.end_time = datetime(2030, 6, 1, 10, 0, tzinfo=UTC)

        with patch("app.services.meetings.bookings_service._crud._load_booking", load_mock):
            with pytest.raises(HTTPException) as exc_info:
                await update_booking(db, booking_id=booking.id, payload=payload, user=user)
        assert exc_info.value.status_code == 422

    async def test_update_with_apply_to_this_clears_series(self):
        from app.schemas.meetings import BookingUpdate
        from app.services.meetings.bookings_service._crud import update_booking

        user = _make_user()
        series_id = uuid.uuid4()
        booking = _make_booking_orm(creator_id=user.id, series_id=series_id)
        db = _make_db_with_booking(booking=booking)
        load_mock = AsyncMock(return_value=booking)

        begin_nested_ctx = AsyncMock()
        begin_nested_ctx.__aenter__ = AsyncMock(return_value=None)
        begin_nested_ctx.__aexit__ = AsyncMock(return_value=None)
        db.begin_nested = MagicMock(return_value=begin_nested_ctx)

        payload = BookingUpdate(apply_to="this")

        with (
            patch("app.services.meetings.bookings_service._crud._load_booking", load_mock),
            patch("app.core.system_config.load_system_settings", return_value=SimpleNamespace(portal_base_url="https://portal.local")),
        ):
            result_booking, diff = await update_booking(
                db, booking_id=booking.id, payload=payload, user=user
            )

        assert booking.series_id is None
        assert diff.old_series_uid is not None


class TestDeleteBooking:
    async def test_delete_not_found_raises_404(self):
        from app.services.meetings.bookings_service._crud import delete_booking

        user = _make_user()
        db = _make_db_with_booking()
        load_mock = AsyncMock(return_value=None)

        with patch("app.services.meetings.bookings_service._crud._load_booking", load_mock):
            with pytest.raises(HTTPException) as exc_info:
                await delete_booking(db, booking_id=uuid.uuid4(), user=user)
        assert exc_info.value.status_code == 404

    async def test_delete_forbidden_for_non_owner(self):
        from app.services.meetings.bookings_service._crud import delete_booking

        user = _make_user(role="user")
        booking = _make_booking_orm(creator_id=uuid.uuid4())
        db = _make_db_with_booking(booking=booking)
        load_mock = AsyncMock(return_value=booking)

        with patch("app.services.meetings.bookings_service._crud._load_booking", load_mock):
            with pytest.raises(HTTPException) as exc_info:
                await delete_booking(db, booking_id=booking.id, user=user)
        assert exc_info.value.status_code == 403

    async def test_delete_success_returns_snapshot(self):
        from app.services.meetings.bookings_service._crud import delete_booking

        user = _make_user()
        booking = _make_booking_orm(creator_id=user.id)
        db = _make_db_with_booking(booking=booking)
        load_mock = AsyncMock(return_value=booking)

        with patch("app.services.meetings.bookings_service._crud._load_booking", load_mock):
            result = await delete_booking(db, booking_id=booking.id, user=user)

        assert result is booking
        db.delete.assert_awaited_once_with(booking)
        db.flush.assert_awaited()

    async def test_delete_by_admin_succeeds(self):
        from app.services.meetings.bookings_service._crud import delete_booking

        admin = _make_user(role="admin")
        other_user_id = uuid.uuid4()
        booking = _make_booking_orm(creator_id=other_user_id)
        db = _make_db_with_booking(booking=booking)
        load_mock = AsyncMock(return_value=booking)

        with patch("app.services.meetings.bookings_service._crud._load_booking", load_mock):
            result = await delete_booking(db, booking_id=booking.id, user=admin)

        assert result is booking
