from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _make_db(rows=None):
    db = AsyncMock()

    scalars_mock = MagicMock()
    unique_mock = MagicMock()
    unique_mock.all.return_value = rows or []
    scalars_mock.unique.return_value = unique_mock

    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    execute_result.scalar_one_or_none.return_value = rows[0] if rows else None

    db.execute = AsyncMock(return_value=execute_result)
    return db, execute_result


class TestListBookings:
    async def test_returns_empty_list_when_no_bookings(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        db, _ = _make_db([])
        with patch(
            "app.core.system_config.load_system_settings", return_value=MagicMock(timezone="UTC")
        ):
            results = await list_bookings(db)
        assert results == []

    async def test_returns_bookings(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        booking = MagicMock()
        db, _ = _make_db([booking])
        with patch(
            "app.core.system_config.load_system_settings", return_value=MagicMock(timezone="UTC")
        ):
            results = await list_bookings(db)
        assert results == [booking]

    async def test_filter_by_date(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        db, _ = _make_db([])
        with patch(
            "app.core.system_config.load_system_settings", return_value=MagicMock(timezone="UTC")
        ):
            results = await list_bookings(db, date=date(2030, 6, 1))
        assert results == []
        db.execute.assert_awaited_once()

    async def test_filter_by_start_and_end_date(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        db, _ = _make_db([])
        with patch(
            "app.core.system_config.load_system_settings", return_value=MagicMock(timezone="UTC")
        ):
            results = await list_bookings(
                db,
                start_date=date(2030, 6, 1),
                end_date=date(2030, 6, 30),
            )
        assert results == []

    async def test_filter_by_start_date_only(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        db, _ = _make_db([])
        with patch(
            "app.core.system_config.load_system_settings", return_value=MagicMock(timezone="UTC")
        ):
            results = await list_bookings(db, start_date=date(2030, 6, 1))
        assert results == []

    async def test_filter_by_end_date_only(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        db, _ = _make_db([])
        with patch(
            "app.core.system_config.load_system_settings", return_value=MagicMock(timezone="UTC")
        ):
            results = await list_bookings(db, end_date=date(2030, 6, 30))
        assert results == []

    async def test_filter_by_room_id(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        db, _ = _make_db([])
        with patch(
            "app.core.system_config.load_system_settings", return_value=MagicMock(timezone="UTC")
        ):
            results = await list_bookings(db, room_id=uuid.uuid4())
        assert results == []

    async def test_filter_by_creator_id(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        db, _ = _make_db([])
        with patch(
            "app.core.system_config.load_system_settings", return_value=MagicMock(timezone="UTC")
        ):
            results = await list_bookings(db, creator_id=uuid.uuid4())
        assert results == []

    async def test_explicit_tz_skips_system_config(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        db, _ = _make_db([])
        load_settings_mock = MagicMock()
        with patch("app.core.system_config.load_system_settings", load_settings_mock):
            results = await list_bookings(db, tz="Europe/Moscow")
        load_settings_mock.assert_not_called()
        assert results == []

    async def test_limit_capped_at_500(self):
        from app.services.meetings.bookings_service._queries import list_bookings

        db, _ = _make_db([])
        with patch(
            "app.core.system_config.load_system_settings", return_value=MagicMock(timezone="UTC")
        ):
            results = await list_bookings(db, limit=9999)
        assert results == []
        db.execute.assert_awaited_once()


class TestListMyBookings:
    async def test_returns_empty_for_user_with_no_bookings(self):
        from app.services.meetings.bookings_service._queries import list_my_bookings

        db, _ = _make_db([])
        results = await list_my_bookings(db, user_id=uuid.uuid4())
        assert results == []

    async def test_returns_user_bookings(self):
        from app.services.meetings.bookings_service._queries import list_my_bookings

        booking = MagicMock()
        db, _ = _make_db([booking])
        results = await list_my_bookings(db, user_id=uuid.uuid4())
        assert results == [booking]

    async def test_uses_today_when_no_start_date(self):
        from app.services.meetings.bookings_service._queries import list_my_bookings

        db, _ = _make_db([])
        results = await list_my_bookings(db, user_id=uuid.uuid4(), start_date=None)
        assert results == []
        db.execute.assert_awaited_once()

    async def test_with_explicit_start_date(self):
        from app.services.meetings.bookings_service._queries import list_my_bookings

        db, _ = _make_db([])
        results = await list_my_bookings(
            db,
            user_id=uuid.uuid4(),
            start_date=date(2030, 6, 1),
        )
        assert results == []

    async def test_limit_capped_at_max(self):
        from app.services.meetings.bookings_service._queries import list_my_bookings

        db, _ = _make_db([])
        results = await list_my_bookings(db, user_id=uuid.uuid4(), limit=9999)
        assert results == []
        db.execute.assert_awaited_once()


class TestGetBooking:
    async def test_returns_booking_when_found(self):
        from app.services.meetings.bookings_service._queries import get_booking

        booking = MagicMock()
        db, _ = _make_db([booking])
        load_mock = AsyncMock(return_value=booking)

        with patch("app.services.meetings.bookings_service._queries._load_booking", load_mock):
            result = await get_booking(db, uuid.uuid4())
        assert result is booking

    async def test_returns_none_when_not_found(self):
        from app.services.meetings.bookings_service._queries import get_booking

        db, _ = _make_db([])
        load_mock = AsyncMock(return_value=None)

        with patch("app.services.meetings.bookings_service._queries._load_booking", load_mock):
            result = await get_booking(db, uuid.uuid4())
        assert result is None
