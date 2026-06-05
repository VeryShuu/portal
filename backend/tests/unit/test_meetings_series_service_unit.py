from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from app.services.meetings import series_service


def _scalars_all_result(items):
    result = MagicMock()
    scal = MagicMock()
    scal.all.return_value = list(items)
    result.scalars.return_value = scal
    return result


def _scalar_one_result(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


class TestLoadBookingsBulk:
    async def test_empty_ids_short_circuits_without_query(self):
        db = MagicMock()
        db.execute = AsyncMock()

        assert await series_service._load_bookings_bulk(db, []) == []
        db.execute.assert_not_awaited()


class TestGetSeriesCount:
    async def test_returns_scalar_one(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalar_one_result(5))

        assert await series_service.get_series_count(db, uuid.uuid4()) == 5


class TestCreateBookingSeries:
    async def test_no_instances_raises_422(self):
        db = MagicMock()
        payload = SimpleNamespace(
            recurrence=SimpleNamespace(),
            start_time=datetime(2030, 1, 1, 9, 0, tzinfo=UTC),
            end_time=datetime(2030, 1, 1, 10, 0, tzinfo=UTC),
            room_ids=[uuid.uuid4()],
            invited_users=[],
        )
        user = SimpleNamespace(id=uuid.uuid4(), email="u@x", full_name="U")

        with (
            patch.object(series_service, "_verify_rooms_active", new=AsyncMock()),
            patch.object(series_service, "expand_recurrence", return_value=[]),
            pytest.raises(HTTPException) as exc,
        ):
            await series_service.create_booking_series(db, payload=payload, user=user)

        assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestUpdateSeries:
    async def test_missing_series_raises_404(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_all_result([]))
        user = SimpleNamespace(id=uuid.uuid4(), role="admin")

        with pytest.raises(HTTPException) as exc:
            await series_service.update_series(
                db, series_id=uuid.uuid4(), payload=MagicMock(), user=user
            )

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_non_owner_non_admin_raises_403(self):
        first = SimpleNamespace(creator_id=uuid.uuid4())
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_all_result([first]))
        user = SimpleNamespace(id=uuid.uuid4(), role="reader")

        with pytest.raises(HTTPException) as exc:
            await series_service.update_series(
                db, series_id=uuid.uuid4(), payload=MagicMock(), user=user
            )

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


class TestDeleteSeries:
    async def test_missing_series_raises_404(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_all_result([]))
        user = SimpleNamespace(id=uuid.uuid4(), role="admin")

        with pytest.raises(HTTPException) as exc:
            await series_service.delete_series(db, series_id=uuid.uuid4(), user=user)

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_non_owner_non_admin_raises_403(self):
        first = SimpleNamespace(creator_id=uuid.uuid4())
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_all_result([first]))
        user = SimpleNamespace(id=uuid.uuid4(), role="reader")

        with pytest.raises(HTTPException) as exc:
            await series_service.delete_series(db, series_id=uuid.uuid4(), user=user)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_owner_deletes_and_returns_snapshots(self):
        creator_id = uuid.uuid4()
        first = SimpleNamespace(creator_id=creator_id)
        select_result = _scalars_all_result([first])
        delete_result = MagicMock()
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[select_result, delete_result])
        db.flush = AsyncMock()
        user = SimpleNamespace(id=creator_id, role="reader")

        snapshots = await series_service.delete_series(
            db, series_id=uuid.uuid4(), user=user
        )

        assert snapshots == [first]
        assert db.execute.await_count == 2
        db.flush.assert_awaited_once()

    async def test_admin_can_delete_foreign_series(self):
        first = SimpleNamespace(creator_id=uuid.uuid4())
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[_scalars_all_result([first]), MagicMock()])
        db.flush = AsyncMock()
        user = SimpleNamespace(id=uuid.uuid4(), role="admin")

        snapshots = await series_service.delete_series(
            db, series_id=uuid.uuid4(), user=user
        )

        assert snapshots == [first]
