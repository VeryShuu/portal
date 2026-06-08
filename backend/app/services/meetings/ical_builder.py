from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from typing import Literal
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, vCalAddress, vText

from app.models.meetings import MeetingBooking


def _resolve_target_tz(portal_tz: str) -> tzinfo:
    try:
        return ZoneInfo(portal_tz)
    except Exception:
        return UTC


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _resolve_uid(booking: MeetingBooking, company_domain: str, uid_override: str | None) -> str:
    if uid_override is not None:
        return uid_override
    if booking.series_id is not None:
        return f"series-{booking.series_id}@{company_domain}"
    return f"{booking.id}@{company_domain}"


def _add_location(event: Event, rooms: list) -> None:
    if not rooms:
        return
    event.add("location", "; ".join(r.name for r in rooms))
    first_link = next((r.link for r in rooms if r.link), None)
    if first_link:
        event.add("url", first_link)


def _add_invited_attendees(event: Event, invited_users: list | None) -> None:
    for invited in invited_users or []:
        attendee = vCalAddress(f"mailto:{invited['email']}")
        attendee.params["cn"] = vText(invited.get("full_name", invited.get("email", "")))
        attendee.params["partstat"] = vText("NEEDS-ACTION")
        attendee.params["rsvp"] = vText("TRUE")
        attendee.params["role"] = vText("REQ-PARTICIPANT")
        attendee.params["cutype"] = vText("INDIVIDUAL")
        event.add("attendee", attendee)


def _add_room_attendees(event: Event, rooms: list) -> None:
    for room_entry in rooms:
        room_email = getattr(room_entry, "email", None)
        if not room_email:
            continue
        room_attendee = vCalAddress(f"mailto:{room_email}")
        room_attendee.params["cn"] = vText(room_entry.name)
        room_attendee.params["cutype"] = vText("RESOURCE")
        room_attendee.params["role"] = vText("NON-PARTICIPANT")
        room_attendee.params["partstat"] = vText("ACCEPTED")
        event.add("attendee", room_attendee)


def build_ical(
    booking: MeetingBooking,
    method: Literal["REQUEST", "CANCEL"],
    company_domain: str,
    from_email: str,
    portal_tz: str | None = None,
    uid_override: str | None = None,
) -> bytes:
    from app.core.system_config import load_system_settings

    if portal_tz is None:
        portal_tz = load_system_settings().timezone

    cal = Calendar()
    cal.add("prodid", "-//Portal//Meetings//RU")
    cal.add("version", "2.0")
    cal.add("method", method)

    rooms = [br.room for br in booking.rooms]
    target_tz = _resolve_target_tz(portal_tz)

    event = Event()
    event.add("uid", _resolve_uid(booking, company_domain, uid_override))
    event.add("sequence", booking.update_count or 0)
    event.add("dtstamp", datetime.now(UTC))
    event.add("dtstart", _as_aware_utc(booking.start_time).astimezone(target_tz))
    event.add("dtend", _as_aware_utc(booking.end_time).astimezone(target_tz))
    event.add("summary", booking.title)
    if booking.description:
        event.add("description", booking.description)

    _add_location(event, rooms)

    organizer = vCalAddress(f"mailto:{from_email}")
    organizer.params["cn"] = vText(booking.organizer_name)
    event.add("organizer", organizer)

    _add_invited_attendees(event, booking.invited_users)
    _add_room_attendees(event, rooms)

    if booking.recurrence_rule:
        event.add("rrule", booking.recurrence_rule)

    cal.add_component(event)
    result: bytes = cal.to_ical()
    return result
