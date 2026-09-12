"""Unit-тесты enrich RSVP в _mappers (booking_to_out / bookings_to_out)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _booking(invited: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="T",
        organizer_name="Org",
        creator_id=None,
        description=None,
        start_time=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 1, 11, 0, tzinfo=UTC),
        invited_users=invited,
        series_id=None,
        recurrence_rule=None,
        update_count=0,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 1, tzinfo=UTC),
        rooms=[],
    )


def _rsvp_map(
    booking_id, email: str, status: Literal["accepted", "declined", "tentative"] = "accepted"
) -> dict:
    from app.schemas.meetings import RsvpInfo

    return {
        booking_id: {
            email.lower(): RsvpInfo(status=status, updated_at=datetime(2026, 8, 20, tzinfo=UTC))
        }
    }


class TestBookingToOutRsvp:
    async def test_single_booking_enriches_rsvp(self):
        from app.api.meetings._mappers import booking_to_out

        booking = _booking([{"user_id": "u1", "full_name": "A", "email": "a@x.com"}])
        with (
            patch(
                "app.api.meetings._mappers.enrich_absences_for_invited",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.api.meetings._mappers.load_rsvp_map",
                AsyncMock(return_value=_rsvp_map(booking.id, "a@x.com")),
            ),
        ):
            out = await booking_to_out(AsyncMock(), booking)
        assert out.invited_users[0].rsvp is not None
        assert out.invited_users[0].rsvp.status == "accepted"

    async def test_no_invited_users_skips_enrich(self):
        from app.api.meetings._mappers import booking_to_out

        booking = _booking([])
        with (
            patch(
                "app.api.meetings._mappers.enrich_absences_for_invited",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.api.meetings._mappers.load_rsvp_map",
                AsyncMock(return_value={}),
            ) as rsvp_mock,
        ):
            out = await booking_to_out(AsyncMock(), booking)
        assert out.invited_users == []
        rsvp_mock.assert_not_awaited()

    async def test_batch_enriches_rsvp(self):
        from app.api.meetings._mappers import bookings_to_out

        b1 = _booking([{"user_id": "u1", "full_name": "A", "email": "a@x.com"}])
        b2 = _booking([{"user_id": "u2", "full_name": "B", "email": "b@x.com"}])
        rsvp = {}
        rsvp.update(_rsvp_map(b1.id, "a@x.com"))
        rsvp.update(_rsvp_map(b2.id, "b@x.com", status="declined"))
        with (
            patch(
                "app.api.meetings._mappers.enrich_absences_for_invited",
                AsyncMock(return_value={}),
            ),
            patch("app.api.meetings._mappers.load_rsvp_map", AsyncMock(return_value=rsvp)),
        ):
            out = await bookings_to_out(AsyncMock(), [b1, b2])
        by_email = {u.email: u for b in out for u in b.invited_users}
        assert by_email["a@x.com"].rsvp.status == "accepted"
        assert by_email["b@x.com"].rsvp.status == "declined"
