"""TST-05: iCal DTSTART/DTEND must be serialized in the portal timezone.

Business requirement: meeting invitations carry the portal-local time
(``TZID=<portal_tz>``) instead of being converted to UTC, so calendar
clients show the same wall-clock time the organizer scheduled.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

icalendar = pytest.importorskip("icalendar")
Calendar = icalendar.Calendar


def _make_room(tz: str = "Europe/Moscow"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Room",
        timezone=tz,
        link=None,
        email=None,
    )


def _make_booking(room):
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="x",
        organizer_name="O",
        description=None,
        start_time=datetime(2030, 1, 15, 7, 0, tzinfo=UTC),
        end_time=datetime(2030, 1, 15, 8, 0, tzinfo=UTC),
        invited_users=[],
        series_id=None,
        recurrence_rule=None,
        update_count=0,
        rooms=[SimpleNamespace(room=room)],
    )


def _get_event_tzids(data: bytes) -> set[str]:
    cal = Calendar.from_ical(data)
    out: set[str] = set()
    for event in cal.walk("VEVENT"):
        for prop in ("DTSTART", "DTEND"):
            val = event.get(prop)
            if val is None:
                continue
            tz = val.params.get("TZID") if hasattr(val, "params") else None
            if tz:
                out.add(str(tz))
    return out


@pytest.mark.parametrize("tz", ["Europe/Moscow", "Asia/Novosibirsk"])
def test_dtstart_dtend_serialized_in_portal_tz(tz: str):
    from app.services.meetings.ical_builder import build_ical

    room = _make_room(tz)
    booking = _make_booking(room)
    data = build_ical(
        booking,
        "REQUEST",
        "portal.local",
        "noreply@portal.local",
        portal_tz=tz,
    )

    assert _get_event_tzids(data) == {tz}, "DTSTART/DTEND must carry portal TZID"
    assert f"TZID={tz}".encode() in data
