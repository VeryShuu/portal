from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, vCalAddress, vText

from app.models.meetings import MeetingBooking


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

    start_utc = booking.start_time
    end_utc = booking.end_time
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=UTC)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=UTC)

    event = Event()
    if uid_override is not None:
        uid = uid_override
    elif booking.series_id is not None:
        uid = f"series-{booking.series_id}@{company_domain}"
    else:
        uid = f"{booking.id}@{company_domain}"
    event.add("uid", uid)
    event.add("sequence", booking.update_count or 0)
    event.add("dtstamp", datetime.now(UTC))
    try:
        portal_zone = ZoneInfo(portal_tz)
    except Exception:
        portal_zone = None
    target_tz = portal_zone if portal_zone is not None else UTC
    event.add("dtstart", start_utc.astimezone(target_tz))
    event.add("dtend", end_utc.astimezone(target_tz))
    event.add("summary", booking.title)
    if booking.description:
        event.add("description", booking.description)

    if rooms:
        event.add("location", "; ".join(r.name for r in rooms))
        first_link = next((r.link for r in rooms if r.link), None)
        if first_link:
            event.add("url", first_link)

    organizer = vCalAddress(f"mailto:{from_email}")
    organizer.params["cn"] = vText(booking.organizer_name)
    event.add("organizer", organizer)

    for invited in booking.invited_users or []:
        attendee = vCalAddress(f"mailto:{invited['email']}")
        attendee.params["cn"] = vText(invited.get("full_name", invited.get("email", "")))
        attendee.params["partstat"] = vText("NEEDS-ACTION")
        attendee.params["rsvp"] = vText("TRUE")
        attendee.params["role"] = vText("REQ-PARTICIPANT")
        attendee.params["cutype"] = vText("INDIVIDUAL")
        event.add("attendee", attendee)

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

    if booking.recurrence_rule:
        event.add("rrule", booking.recurrence_rule)

    cal.add_component(event)
    result: bytes = cal.to_ical()
    return result
