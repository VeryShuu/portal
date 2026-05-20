"""Unit tests for Pydantic schemas of the meetings module."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError


def _start_end():
    start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
    end = datetime(2030, 1, 1, 11, 0, tzinfo=UTC)
    return start, end


class TestRoomSchemas:
    def test_room_create_defaults_and_valid_timezone(self):
        from app.schemas.meetings import RoomCreate

        rc = RoomCreate(name="Sochi")
        assert rc.timezone == "Europe/Moscow"
        assert rc.sort_order == 0

    def test_room_create_rejects_unknown_timezone(self):
        from app.schemas.meetings import RoomCreate

        with pytest.raises(ValidationError):
            RoomCreate(name="Bad", timezone="No/Such_Zone")

    def test_room_create_empty_name(self):
        from app.schemas.meetings import RoomCreate

        with pytest.raises(ValidationError):
            RoomCreate(name="")

    def test_room_update_partial_with_none_timezone_ok(self):
        from app.schemas.meetings import RoomUpdate

        ru = RoomUpdate(name="Renamed")
        assert ru.timezone is None

    def test_room_update_invalid_timezone(self):
        from app.schemas.meetings import RoomUpdate

        with pytest.raises(ValidationError):
            RoomUpdate(timezone="Atlantis/Lost")


class TestBookingSchemas:
    def test_booking_create_valid(self):
        from app.schemas.meetings import BookingCreate

        start, end = _start_end()
        bc = BookingCreate(
            title="Standup",
            start_time=start,
            end_time=end,
            room_ids=[uuid.uuid4()],
        )
        assert bc.invited_users == []
        assert bc.recurrence is None

    def test_booking_create_end_before_start_fails(self):
        from app.schemas.meetings import BookingCreate

        start, end = _start_end()
        with pytest.raises(ValidationError):
            BookingCreate(
                title="Bad",
                start_time=end,
                end_time=start,
                room_ids=[uuid.uuid4()],
            )

    def test_booking_create_equal_times_fails(self):
        from app.schemas.meetings import BookingCreate

        start, _ = _start_end()
        with pytest.raises(ValidationError):
            BookingCreate(
                title="Zero",
                start_time=start,
                end_time=start,
                room_ids=[uuid.uuid4()],
            )

    def test_booking_create_requires_at_least_one_room(self):
        from app.schemas.meetings import BookingCreate

        start, end = _start_end()
        with pytest.raises(ValidationError):
            BookingCreate(title="x", start_time=start, end_time=end, room_ids=[])

    def test_booking_create_rejects_duplicate_rooms(self):
        from app.schemas.meetings import BookingCreate

        start, end = _start_end()
        rid = uuid.uuid4()
        with pytest.raises(ValidationError):
            BookingCreate(
                title="dup", start_time=start, end_time=end, room_ids=[rid, rid]
            )

    def test_booking_update_partial_allows_only_title(self):
        from app.schemas.meetings import BookingUpdate

        bu = BookingUpdate(title="renamed")
        assert bu.apply_to == "this"
        assert bu.start_time is None

    def test_booking_update_end_before_start(self):
        from app.schemas.meetings import BookingUpdate

        start, end = _start_end()
        with pytest.raises(ValidationError):
            BookingUpdate(start_time=end, end_time=start)

    def test_booking_update_duplicate_rooms(self):
        from app.schemas.meetings import BookingUpdate

        rid = uuid.uuid4()
        with pytest.raises(ValidationError):
            BookingUpdate(room_ids=[rid, rid])

    def test_invited_user_validates_email(self):
        from app.schemas.meetings import InvitedUser

        with pytest.raises(ValidationError):
            InvitedUser(user_id="u-1", full_name="X", email="not-an-email")

    def test_booking_list_params_clamps(self):
        from app.schemas.meetings import BookingListParams

        p = BookingListParams()
        assert p.limit == 500 and p.offset == 0
        with pytest.raises(ValidationError):
            BookingListParams(limit=0)
        with pytest.raises(ValidationError):
            BookingListParams(limit=501)
        with pytest.raises(ValidationError):
            BookingListParams(offset=-1)


class TestSeriesSchemas:
    def test_series_update_end_before_start(self):
        from app.schemas.meetings import SeriesUpdate

        start, end = _start_end()
        with pytest.raises(ValidationError):
            SeriesUpdate(start_time=end, end_time=start)

    def test_series_update_duplicate_rooms(self):
        from app.schemas.meetings import SeriesUpdate

        rid = uuid.uuid4()
        with pytest.raises(ValidationError):
            SeriesUpdate(room_ids=[rid, rid])

    def test_recurrence_rule_freq_literal(self):
        from app.schemas.meetings import RecurrenceRule

        rr = RecurrenceRule(freq="DAILY", until_date=date(2030, 1, 31))
        assert rr.freq == "DAILY"
        with pytest.raises(ValidationError):
            RecurrenceRule(freq="HOURLY", until_date=date(2030, 1, 31))


class TestComputeDiff:
    def test_skips_malformed_users_missing_user_id(self):
        from app.schemas.meetings import InvitedUser
        from app.services.meetings.bookings_service import _compute_diff

        old = [
            {"user_id": "u1", "full_name": "Alice", "email": "alice@x.com"},
            {"full_name": "Ghost", "email": "ghost@x.com"},
        ]
        new = [InvitedUser(user_id="u1", full_name="Alice", email="alice@x.com")]
        diff = _compute_diff(old, new, non_participant_changed=False)
        assert len(diff.unchanged_users) == 1
        assert diff.unchanged_users[0].user_id == "u1"
        assert all(u.email != "ghost@x.com" for u in diff.removed_users)

    def test_skips_malformed_users_missing_email(self):
        from app.schemas.meetings import InvitedUser
        from app.services.meetings.bookings_service import _compute_diff

        old = [
            {"user_id": "u1", "full_name": "Alice", "email": "alice@x.com"},
            {"user_id": "u2", "full_name": "NoEmail"},
        ]
        new = [InvitedUser(user_id="u1", full_name="Alice", email="alice@x.com")]
        diff = _compute_diff(old, new, non_participant_changed=False)
        assert len(diff.unchanged_users) == 1
        assert not any(u.user_id == "u2" for u in diff.removed_users)

    def test_added_removed_unchanged_split(self):
        from app.schemas.meetings import InvitedUser
        from app.services.meetings.bookings_service import _compute_diff

        old = [
            {"user_id": "u1", "full_name": "Alice", "email": "alice@x.com"},
            {"user_id": "u2", "full_name": "Bob", "email": "bob@x.com"},
        ]
        new = [
            InvitedUser(user_id="u2", full_name="Bob", email="bob@x.com"),
            InvitedUser(user_id="u3", full_name="Carol", email="carol@x.com"),
        ]
        diff = _compute_diff(old, new, non_participant_changed=True)
        assert any(u.user_id == "u3" for u in diff.added_users)
        assert any(u.user_id == "u1" for u in diff.removed_users)
        assert any(u.user_id == "u2" for u in diff.unchanged_users)
        assert diff.non_participant_changed is True
