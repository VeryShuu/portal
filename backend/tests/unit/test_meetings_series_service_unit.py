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


def _scalars_unique_all_result(items):
    """Для запросов с ``.scalars().unique().all()`` (selectinload — _load_bookings_bulk)."""
    result = MagicMock()
    scal = MagicMock()
    scal.unique.return_value.all.return_value = list(items)
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

        snapshots = await series_service.delete_series(db, series_id=uuid.uuid4(), user=user)

        assert snapshots == [first]
        assert db.execute.await_count == 2
        db.flush.assert_awaited_once()

    async def test_admin_can_delete_foreign_series(self):
        first = SimpleNamespace(creator_id=uuid.uuid4())
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[_scalars_all_result([first]), MagicMock()])
        db.flush = AsyncMock()
        user = SimpleNamespace(id=uuid.uuid4(), role="admin")

        snapshots = await series_service.delete_series(db, series_id=uuid.uuid4(), user=user)

        assert snapshots == [first]


# ---------------------------------------------------------------------------
# Чистые helper-функции — без БД, легко покрываются напрямую.
# ---------------------------------------------------------------------------


class TestLoadBookingsBulkNonEmpty:
    async def test_loads_bookings_in_start_time_order(self):
        """Не-empty путь: выполняет select и возвращает scalars().unique().all()."""
        b1, b2 = SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_unique_all_result([b1, b2]))

        out = await series_service._load_bookings_bulk(db, [b1.id, b2.id])

        assert out == [b1, b2]
        db.execute.assert_awaited_once()


class TestEnsureSeriesEditable:
    def test_owner_ok(self):
        creator_id = uuid.uuid4()
        first = SimpleNamespace(creator_id=creator_id)
        user = SimpleNamespace(id=creator_id, role="reader")
        # Не падает — владелец может редактировать.
        series_service._ensure_series_editable(first, user)

    def test_admin_ok(self):
        first = SimpleNamespace(creator_id=uuid.uuid4())
        user = SimpleNamespace(id=uuid.uuid4(), role="admin")
        series_service._ensure_series_editable(first, user)

    def test_non_owner_non_admin_raises_403(self):
        first = SimpleNamespace(creator_id=uuid.uuid4())
        user = SimpleNamespace(id=uuid.uuid4(), role="editor")
        with pytest.raises(HTTPException) as exc:
            series_service._ensure_series_editable(first, user)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


class TestResolveNewInvited:
    def test_returns_payload_invited_when_provided(self):
        from app.schemas.meetings import InvitedUser

        invited = [InvitedUser(user_id=str(uuid.uuid4()), full_name="A", email="a@example.com")]
        payload = SimpleNamespace(invited_users=invited)
        out = series_service._resolve_new_invited(payload, old_invited=[])
        assert out == invited

    def test_falls_back_to_old_invited_when_payload_none(self):
        old_uid = uuid.uuid4()
        old_invited = [{"user_id": str(old_uid), "full_name": "B", "email": "b@example.com"}]
        payload = SimpleNamespace(invited_users=None)
        out = series_service._resolve_new_invited(payload, old_invited=old_invited)
        assert len(out) == 1
        assert out[0].user_id == str(old_uid)


class TestHasNonParticipantChange:
    def _first(self, **kw):
        base = dict(title="T", description="D")
        base.update(kw)
        return SimpleNamespace(**base)

    def test_no_changes_returns_false(self):
        payload = SimpleNamespace(
            title=None, description=None, start_time=None, end_time=None, room_ids=None
        )
        assert series_service._has_non_participant_change(payload, self._first()) is False

    def test_title_changed_returns_true(self):
        payload = SimpleNamespace(
            title="New", description=None, start_time=None, end_time=None, room_ids=None
        )
        assert series_service._has_non_participant_change(payload, self._first(title="Old")) is True

    def test_same_title_returns_false(self):
        payload = SimpleNamespace(
            title="T", description=None, start_time=None, end_time=None, room_ids=None
        )
        assert series_service._has_non_participant_change(payload, self._first(title="T")) is False

    def test_time_or_rooms_change_returns_true(self):
        from datetime import timedelta

        start = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)
        payload = SimpleNamespace(
            title=None,
            description=None,
            start_time=start + timedelta(hours=1),
            end_time=None,
            room_ids=None,
        )
        assert series_service._has_non_participant_change(payload, self._first()) is True


class TestComputeSeriesDeltas:
    def test_no_times_returns_none_none(self):

        first = SimpleNamespace(
            start_time=datetime(2030, 1, 1, 9, 0, tzinfo=UTC),
            end_time=datetime(2030, 1, 1, 10, 0, tzinfo=UTC),
        )
        payload = SimpleNamespace(start_time=None, end_time=None)
        sd, ed = series_service._compute_series_deltas(payload, first)
        assert sd is None
        assert ed is None

    def test_start_delta_relative_to_first(self):
        from datetime import timedelta

        first = SimpleNamespace(
            start_time=datetime(2030, 1, 1, 9, 0, tzinfo=UTC),
            end_time=datetime(2030, 1, 1, 10, 0, tzinfo=UTC),
        )
        payload = SimpleNamespace(
            start_time=datetime(2030, 1, 1, 11, 0, tzinfo=UTC),  # +2h
            end_time=None,
        )
        sd, ed = series_service._compute_series_deltas(payload, first)
        assert sd == timedelta(hours=2)
        assert ed is None


class TestRecomputeCanonicalRrule:
    def test_no_delta_no_op(self):
        first = SimpleNamespace(
            start_time=datetime(2030, 1, 1, 9, 0, tzinfo=UTC),
            recurrence_rule="FREQ=WEEKLY;UNTIL=20300108;BYDAY=MO",
        )
        original = first.recurrence_rule
        series_service._recompute_canonical_rrule(first, start_delta=None)
        assert first.recurrence_rule == original  # не изменён

    def test_no_recurrence_rule_no_op(self):
        first = SimpleNamespace(
            start_time=datetime(2030, 1, 1, 9, 0, tzinfo=UTC), recurrence_rule=None
        )
        from datetime import timedelta

        series_service._recompute_canonical_rrule(first, start_delta=timedelta(hours=2))
        assert first.recurrence_rule is None

    def test_delta_shifts_start_in_rrule(self):
        """При сдвиге DTSTART пересчитывает RRULE с новым start_time."""
        from datetime import timedelta

        first = SimpleNamespace(
            start_time=datetime(2030, 1, 1, 9, 0, tzinfo=UTC),  # среда
            recurrence_rule="FREQ=WEEKLY;UNTIL=20300228;BYDAY=WE",
        )
        series_service._recompute_canonical_rrule(first, start_delta=timedelta(days=1))
        # Новый rrule построен от start_time + delta (четверг 2030-01-02).
        assert first.recurrence_rule is not None
        assert "UNTIL=20300228" in first.recurrence_rule


# ---------------------------------------------------------------------------
# _apply_series_update_to_booking — вся логика применения апдейта.
# ---------------------------------------------------------------------------


def _booking(**kw):
    """Mutable SimpleNamespace-букинг с комнатами (как MeetingBooking)."""
    base = dict(
        id=uuid.uuid4(),
        title="Old Title",
        description="Old Desc",
        invited_users=[],
        start_time=datetime(2030, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2030, 1, 1, 10, 0, tzinfo=UTC),
        rooms=[],
        update_count=0,
        updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestApplySeriesUpdateToBooking:
    async def test_title_and_description_applied(self):
        db = MagicMock()
        booking = _booking()
        payload = SimpleNamespace(
            title="New Title",
            description="New Desc",
            invited_users=None,
            start_time=None,
            end_time=None,
            room_ids=None,
        )
        now_utc = datetime.now(UTC)

        await series_service._apply_series_update_to_booking(
            db,
            booking,
            payload=payload,
            invited_data=[],
            start_delta=None,
            end_delta=None,
            room_ids_snapshot={},
            non_participant_changed=True,
            now_utc=now_utc,
        )

        assert booking.title == "New Title"
        assert booking.description == "New Desc"
        assert booking.update_count == 1  # non_participant_changed → инкремент
        assert booking.updated_at == now_utc

    async def test_invited_users_applied_when_provided(self):
        db = MagicMock()
        booking = _booking()
        invited_data = [{"user_id": str(uuid.uuid4())}]
        payload = SimpleNamespace(
            title=None,
            description=None,
            invited_users=[object()],  # любой truthy — triggers branch
            start_time=None,
            end_time=None,
            room_ids=None,
        )

        await series_service._apply_series_update_to_booking(
            db,
            booking,
            payload=payload,
            invited_data=invited_data,
            start_delta=None,
            end_delta=None,
            room_ids_snapshot={},
            non_participant_changed=False,
            now_utc=datetime.now(UTC),
        )

        assert booking.invited_users == invited_data

    async def test_time_change_triggers_rebuild_rooms(self):
        """start_delta/end_delta → _rebuild_booking_rooms (delete + add)."""
        from datetime import timedelta

        db = MagicMock()
        db.execute = AsyncMock()
        db.add = MagicMock()
        booking = _booking()
        payload = SimpleNamespace(
            title=None,
            description=None,
            invited_users=None,
            start_time=None,
            end_time=None,
            room_ids=None,
        )

        with patch.object(series_service, "_rebuild_booking_rooms", new=AsyncMock()) as rebuild:
            await series_service._apply_series_update_to_booking(
                db,
                booking,
                payload=payload,
                invited_data=[],
                start_delta=timedelta(hours=1),
                end_delta=None,
                room_ids_snapshot={booking.id: []},
                non_participant_changed=False,
                now_utc=datetime.now(UTC),
            )

        rebuild.assert_awaited_once()
        # В kwargs передаётся new_start = start_time + delta.
        _kwargs = rebuild.await_args.kwargs
        assert _kwargs["new_start"] == booking.start_time + timedelta(hours=1)

    async def test_rooms_change_without_time_uses_snapshot(self):
        """room_ids changed, но time нет → rebuild с room_ids из snapshot."""
        db = MagicMock()
        db.execute = AsyncMock()
        booking = _booking()
        room_a = uuid.uuid4()
        payload = SimpleNamespace(
            title=None,
            description=None,
            invited_users=None,
            start_time=None,
            end_time=None,
            room_ids=[room_a],
        )

        with patch.object(series_service, "_rebuild_booking_rooms", new=AsyncMock()) as rebuild:
            await series_service._apply_series_update_to_booking(
                db,
                booking,
                payload=payload,
                invited_data=[],
                start_delta=None,
                end_delta=None,
                room_ids_snapshot={booking.id: [room_a]},
                non_participant_changed=False,
                now_utc=datetime.now(UTC),
            )

        rebuild.assert_awaited_once()
        assert rebuild.await_args.kwargs["room_ids"] == [room_a]

    async def test_no_changes_no_rebuild_no_update_count(self):
        db = MagicMock()
        booking = _booking(update_count=5)
        payload = SimpleNamespace(
            title=None,
            description=None,
            invited_users=None,
            start_time=None,
            end_time=None,
            room_ids=None,
        )

        with patch.object(series_service, "_rebuild_booking_rooms", new=AsyncMock()) as rebuild:
            await series_service._apply_series_update_to_booking(
                db,
                booking,
                payload=payload,
                invited_data=[],
                start_delta=None,
                end_delta=None,
                room_ids_snapshot={},
                non_participant_changed=False,
                now_utc=datetime.now(UTC),
            )

        rebuild.assert_not_awaited()
        assert booking.update_count == 5  # не инкрементирован


# ---------------------------------------------------------------------------
# create_booking_series — happy path (несколько инстансов, flush, reload).
# ---------------------------------------------------------------------------


class TestCreateBookingSeriesHappyPath:
    async def test_creates_instances_and_reloads(self):
        """Happy path: 2 инстанса → 2 booking + MeetingBookingRoom на каждый,
        flush на каждом, финальный reload через _load_bookings_bulk."""
        from datetime import timedelta

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        start = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)
        end = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        room_id = uuid.uuid4()

        inst1_start = start
        inst1_end = end
        inst2_start = start + timedelta(days=7)
        inst2_end = end + timedelta(days=7)

        payload = SimpleNamespace(
            title="Standup",
            description="Daily",
            start_time=start,
            end_time=end,
            room_ids=[room_id],
            invited_users=[],
            recurrence=SimpleNamespace(),
        )
        user = SimpleNamespace(id=uuid.uuid4(), email="u@x", full_name="Org")

        reloaded = [SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())]

        # Мокаем begin_nested для conflict-проверки (возвращает async CM).
        nested_cm = MagicMock()
        nested_cm.__aenter__ = AsyncMock()
        nested_cm.__aexit__ = AsyncMock()

        with (
            patch.object(series_service, "_verify_rooms_active", new=AsyncMock()),
            patch.object(
                series_service,
                "expand_recurrence",
                return_value=[(inst1_start, inst1_end), (inst2_start, inst2_end)],
            ),
            patch.object(
                series_service, "build_rrule_string", return_value="FREQ=WEEKLY;UNTIL=20300228"
            ),
            patch.object(
                series_service, "_load_bookings_bulk", new=AsyncMock(return_value=reloaded)
            ),
        ):
            db.begin_nested = MagicMock(return_value=nested_cm)
            result = await series_service.create_booking_series(db, payload=payload, user=user)

        assert result == reloaded
        # 2 booking + 2 MeetingBookingRoom = 4 add-вызова.
        assert db.add.call_count == 4
        # flush: 2 per-instance + 1 final? Нет — flush в цикле (2) + nested flush (2).
        assert db.flush.await_count >= 2


# ---------------------------------------------------------------------------
# update_series — happy path (load → editable → apply → flush → reload).
# ---------------------------------------------------------------------------


class TestUpdateSeriesHappyPath:
    async def test_owner_updates_title_and_reloads(self):
        """Владелец меняет title → _apply_series_update_to_booking для каждого,
        финальный reload возвращает обновлённые букинги + diff."""
        creator_id = uuid.uuid4()
        from app.schemas.meetings import SeriesUpdate

        first = _booking(creator_id=creator_id, title="Old")
        second = _booking(creator_id=creator_id, title="Old")

        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_all_result([first, second]))

        reloaded = [SimpleNamespace(id=first.id), SimpleNamespace(id=second.id)]

        payload = SeriesUpdate(title="New Title")

        nested_cm = MagicMock()
        nested_cm.__aenter__ = AsyncMock()
        nested_cm.__aexit__ = AsyncMock()
        db.begin_nested = MagicMock(return_value=nested_cm)

        with (
            patch.object(
                series_service, "_apply_series_update_to_booking", new=AsyncMock()
            ) as apply_mock,
            patch.object(
                series_service, "_load_bookings_bulk", new=AsyncMock(return_value=reloaded)
            ),
        ):
            result, diff = await series_service.update_series(
                db,
                series_id=uuid.uuid4(),
                payload=payload,
                user=SimpleNamespace(id=creator_id, role="reader"),
            )

        assert result == reloaded
        # apply вызван для каждого букинга (2).
        assert apply_mock.await_count == 2
        assert diff is not None  # _compute_diff возвращает объект

    async def test_room_ids_verified_when_provided(self):
        """payload.room_ids не None → _verify_rooms_active вызывается."""
        creator_id = uuid.uuid4()
        from app.schemas.meetings import SeriesUpdate

        first = _booking(creator_id=creator_id)
        db = MagicMock()
        db.execute = AsyncMock(return_value=_scalars_all_result([first]))

        room = uuid.uuid4()
        payload = SeriesUpdate(room_ids=[room])

        nested_cm = MagicMock()
        nested_cm.__aenter__ = AsyncMock()
        nested_cm.__aexit__ = AsyncMock()
        db.begin_nested = MagicMock(return_value=nested_cm)

        with (
            patch.object(series_service, "_verify_rooms_active", new=AsyncMock()) as verify,
            patch.object(series_service, "_apply_series_update_to_booking", new=AsyncMock()),
            patch.object(
                series_service, "_load_bookings_bulk", new=AsyncMock(return_value=[first])
            ),
        ):
            await series_service.update_series(
                db,
                series_id=uuid.uuid4(),
                payload=payload,
                user=SimpleNamespace(id=creator_id, role="reader"),
            )

        verify.assert_awaited_once_with(db, [room])
