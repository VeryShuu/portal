from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, Timezone, TimezoneStandard, vCalAddress, vText

from app.models.meetings import MeetingBooking


def _build_vtimezone(tz_name: str) -> Timezone:
    """Build a minimal VTIMEZONE component for the given IANA timezone.

    Prefers `Timezone.from_tzinfo` (icalendar >= 5.0.10); falls back to a
    minimal STANDARD subcomponent built from the current offset.
    """
    tz_info = ZoneInfo(tz_name)
    factory = getattr(Timezone, "from_tzinfo", None)
    if callable(factory):
        try:
            tz_component = factory(tz_info, tzid=tz_name)
            if tz_component is not None:
                return tz_component
        except Exception:
            pass

    tz_component = Timezone()
    tz_component.add("tzid", tz_name)

    now_local = datetime.now(tz_info)
    offset = tz_info.utcoffset(now_local) or timedelta(0)
    tz_name_short = tz_info.tzname(now_local) or tz_name

    standard = TimezoneStandard()
    standard.add("dtstart", datetime(1970, 1, 1, 0, 0, 0))
    standard.add("tzoffsetfrom", offset)
    standard.add("tzoffsetto", offset)
    standard.add("tzname", tz_name_short)
    tz_component.add_component(standard)
    return tz_component


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

    cal.add_component(_build_vtimezone(portal_tz))

    rooms = [br.room for br in booking.rooms]
    tz_info = ZoneInfo(portal_tz)

    start_utc = booking.start_time
    end_utc = booking.end_time
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=UTC)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=UTC)

    start_local = start_utc.astimezone(tz_info)
    end_local = end_utc.astimezone(tz_info)

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
    event.add("dtstart", start_local)
    event.add("dtend", end_local)
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

    for invited in (booking.invited_users or []):
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
    return cal.to_ical()
