"""TST-05: iCal output must include a VTIMEZONE component matching DTSTART TZID."""

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


def _get_vtimezone_tzids(data: bytes) -> set[str]:
    cal = Calendar.from_ical(data)
    out: set[str] = set()
    for comp in cal.walk("VTIMEZONE"):
        out.add(str(comp.get("TZID")))
    return out


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


def test_vtimezone_component_present_for_dtstart_tzid():
    from app.services.meetings.ical_builder import build_ical

    room = _make_room("Europe/Moscow")
    booking = _make_booking(room)
    data = build_ical(
        booking,
        "REQUEST",
        "portal.local",
        "noreply@portal.local",
        portal_tz="Europe/Moscow",
    )

    vtz = _get_vtimezone_tzids(data)
    evt = _get_event_tzids(data)
    assert "Europe/Moscow" in vtz, f"missing VTIMEZONE for Europe/Moscow, found: {vtz}"
    assert evt.issubset(vtz), f"DTSTART/DTEND TZIDs {evt} not all covered by VTIMEZONE {vtz}"


def test_vtimezone_component_for_non_default_tz():
    from app.services.meetings.ical_builder import build_ical

    room = _make_room("Asia/Novosibirsk")
    booking = _make_booking(room)
    data = build_ical(
        booking,
        "REQUEST",
        "portal.local",
        "noreply@portal.local",
        portal_tz="Asia/Novosibirsk",
    )
    vtz = _get_vtimezone_tzids(data)
    assert "Asia/Novosibirsk" in vtz
