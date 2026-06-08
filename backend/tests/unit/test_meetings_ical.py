"""Unit tests for the iCal builder of the meetings module."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace


def _make_room(name="Zoom Gold", tz="Europe/Moscow", link=None, email=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        timezone=tz,
        link=link,
        email=email,
    )


def _make_booking(
    *,
    rooms,
    invited=None,
    series_id=None,
    update_count=0,
    rrule=None,
    description=None,
):
    booking_id = uuid.uuid4()
    return SimpleNamespace(
        id=booking_id,
        title="Standup",
        organizer_name="Alice",
        description=description,
        start_time=datetime(2030, 1, 15, 7, 0, tzinfo=UTC),  # 10:00 Moscow
        end_time=datetime(2030, 1, 15, 8, 0, tzinfo=UTC),  # 11:00 Moscow
        invited_users=invited or [],
        series_id=series_id,
        recurrence_rule=rrule,
        update_count=update_count,
        rooms=[SimpleNamespace(room=r) for r in rooms],
    )


class TestBuildIcal:
    def test_request_includes_basic_fields(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room()
        booking = _make_booking(rooms=[room])
        data = build_ical(booking, "REQUEST", "portal.local", "noreply@portal.local")
        text = data.decode("utf-8")
        assert "METHOD:REQUEST" in text
        assert "SUMMARY:Standup" in text
        assert f"UID:{booking.id}@portal.local" in text
        assert "TZID=Europe/Moscow" in text
        assert "ORGANIZER" in text
        assert "Alice" in text

    def test_cancel_method(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room()
        booking = _make_booking(rooms=[room])
        data = build_ical(booking, "CANCEL", "portal.local", "noreply@portal.local")
        assert b"METHOD:CANCEL" in data

    def test_series_uid_uses_series_id(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room()
        series = uuid.uuid4()
        booking = _make_booking(rooms=[room], series_id=series, rrule="FREQ=DAILY")
        data = build_ical(booking, "REQUEST", "portal.local", "noreply@portal.local")
        text = data.decode("utf-8")
        assert f"UID:series-{series}@portal.local" in text
        assert "RRULE:FREQ=DAILY" in text

    def test_sequence_uses_update_count(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room()
        booking = _make_booking(rooms=[room], update_count=5)
        text = build_ical(booking, "REQUEST", "portal.local", "noreply@portal.local").decode(
            "utf-8"
        )
        assert "SEQUENCE:5" in text

    def test_attendees_included_with_partstat(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room()
        booking = _make_booking(
            rooms=[room],
            invited=[
                {"user_id": "u1", "full_name": "Bob", "email": "bob@x.com"},
                {"user_id": "u2", "full_name": "Eve", "email": "eve@x.com"},
            ],
        )
        text = build_ical(booking, "REQUEST", "portal.local", "noreply@portal.local").decode(
            "utf-8"
        )
        assert "bob@x.com" in text
        assert "eve@x.com" in text
        assert "PARTSTAT=NEEDS-ACTION" in text
        assert "RSVP=TRUE" in text

    def test_url_from_first_room_link(self):
        from app.services.meetings.ical_builder import build_ical

        rooms = [
            _make_room("Plain"),
            _make_room("Zoom", link="https://zoom.example/abcd"),
        ]
        booking = _make_booking(rooms=rooms)
        text = build_ical(booking, "REQUEST", "portal.local", "noreply@portal.local").decode(
            "utf-8"
        )
        assert "URL:https://zoom.example/abcd" in text
        assert "LOCATION:Plain; Zoom" in text or "LOCATION:Plain\\; Zoom" in text

    def test_naive_datetimes_are_treated_as_utc(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room()
        booking = _make_booking(rooms=[room])
        booking.start_time = datetime(2030, 1, 15, 7, 0)
        booking.end_time = datetime(2030, 1, 15, 8, 0)
        text = build_ical(booking, "REQUEST", "portal.local", "noreply@portal.local").decode(
            "utf-8"
        )
        assert "DTSTART;TZID=Europe/Moscow:20300115T100000" in text
        assert "DTEND;TZID=Europe/Moscow:20300115T110000" in text

    def test_build_ical_uses_explicit_portal_tz_not_room_tz(self):
        from app.services.meetings.ical_builder import build_ical

        room_moscow = _make_room("Moscow Room", tz="Europe/Moscow")
        room_novosibirsk = _make_room("Novosibirsk Room", tz="Asia/Novosibirsk")
        booking = _make_booking(rooms=[room_moscow, room_novosibirsk])
        text = build_ical(
            booking,
            "REQUEST",
            "portal.local",
            "noreply@portal.local",
            portal_tz="Asia/Novosibirsk",
        ).decode("utf-8")
        assert "TZID=Asia/Novosibirsk" in text
        assert "TZID=Europe/Moscow" not in text

    def test_room_with_email_added_as_resource_attendee(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room("Board Room", email="board@x.com")
        booking = _make_booking(rooms=[room])
        raw = build_ical(booking, "REQUEST", "portal.local", "noreply@portal.local").decode("utf-8")
        text = raw.replace("\r\n ", "")
        assert "board@x.com" in text
        assert "CUTYPE=RESOURCE" in text
        assert "ROLE=NON-PARTICIPANT" in text
        assert "PARTSTAT=ACCEPTED" in text

    def test_invalid_portal_tz_falls_back_to_utc(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room()
        booking = _make_booking(rooms=[room])
        text = build_ical(
            booking,
            "REQUEST",
            "portal.local",
            "noreply@portal.local",
            portal_tz="Not/AZone",
        ).decode("utf-8")
        assert "DTSTART:20300115T070000Z" in text
        assert "DTEND:20300115T080000Z" in text

    def test_uid_override_takes_precedence(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room()
        series = uuid.uuid4()
        booking = _make_booking(rooms=[room], series_id=series)
        text = build_ical(
            booking,
            "REQUEST",
            "portal.local",
            "noreply@portal.local",
            uid_override="custom-uid@portal.local",
        ).decode("utf-8")
        assert "UID:custom-uid@portal.local" in text
        assert f"series-{series}" not in text

    def test_description_included_when_present(self):
        from app.services.meetings.ical_builder import build_ical

        room = _make_room()
        booking = _make_booking(rooms=[room], description="Sync about Q3")
        text = build_ical(booking, "REQUEST", "portal.local", "noreply@portal.local").decode(
            "utf-8"
        )
        assert "DESCRIPTION:Sync about Q3" in text

    def test_no_rooms_omits_location_and_url(self):
        from app.services.meetings.ical_builder import build_ical

        booking = _make_booking(rooms=[])
        text = build_ical(booking, "REQUEST", "portal.local", "noreply@portal.local").decode(
            "utf-8"
        )
        assert "LOCATION" not in text
        assert "URL" not in text

    def test_build_ical_multi_tz_rooms_uses_portal_tz(self):
        from app.services.meetings.ical_builder import build_ical

        rooms = [
            _make_room("Room A", tz="Europe/London"),
            _make_room("Room B", tz="America/New_York"),
            _make_room("Room C", tz="Asia/Tokyo"),
        ]
        booking = _make_booking(rooms=rooms)
        text = build_ical(
            booking,
            "REQUEST",
            "portal.local",
            "noreply@portal.local",
            portal_tz="Europe/Moscow",
        ).decode("utf-8")
        assert "TZID=Europe/Moscow" in text
        assert "TZID=Europe/London" not in text
        assert "TZID=America/New_York" not in text
        assert "TZID=Asia/Tokyo" not in text
