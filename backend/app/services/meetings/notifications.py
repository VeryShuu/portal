from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.meetings import MeetingBooking
    from app.services.meetings.bookings_service import BookingDiff

logger = get_logger(__name__)


async def dispatch_meeting_emails(
    *,
    booking: MeetingBooking,
    action: Literal["created", "updated", "cancelled"],
    diff: BookingDiff | None = None,
) -> None:
    """Записывает в email_outbox по строке на каждого получателя.

    iCal строится максимум дважды (REQUEST/CANCEL). Outbox-dispatcher
    в воркере периодически забирает PENDING и шлёт через SMTP
    (см. app.worker.tasks.email_outbox.process_email_outbox).
    """
    from urllib.parse import urlparse

    from app.core.database import AsyncSessionLocal
    from app.core.system_config import load_system_settings
    from app.services.meetings.ical_builder import build_ical

    sys_cfg = load_system_settings()
    raw_url = getattr(sys_cfg, "portal_base_url", "portal.company.local")
    parsed_url = urlparse(raw_url if "://" in raw_url else f"//{raw_url}")
    company_domain = parsed_url.hostname or raw_url
    from_email = _get_from_email()

    cache: dict[str, bytes] = {}

    def _ical(method: Literal["REQUEST", "CANCEL"]) -> bytes:
        if method not in cache:
            cache[method] = build_ical(
                booking, method=method, company_domain=company_domain, from_email=from_email
            )
        return cache[method]

    def _ical_with_uid(method: Literal["REQUEST", "CANCEL"], uid_override: str) -> bytes:
        return build_ical(
            booking,
            method=method,
            company_domain=company_domain,
            from_email=from_email,
            uid_override=uid_override,
        )

    invited_emails: set[str] = {
        u.get("email", "") if isinstance(u, dict) else getattr(u, "email", "")
        for u in (booking.invited_users or [])
    }
    invited_emails.discard("")

    async with AsyncSessionLocal() as session, session.begin():
        organizer_user = await _load_organizer(session, booking)
        already_notified: set[str] = set(invited_emails)

        if action == "created":
            ical_bytes = _ical("REQUEST")
            for user in list(booking.invited_users or []):
                await _enqueue(session, booking, user, "REQUEST", ical_bytes)
            await _enqueue_organizer(
                session, booking, organizer_user, "REQUEST", ical_bytes, already_notified
            )
            await _enqueue_room_emails(session, booking, "REQUEST", ical_bytes, already_notified)

        elif action == "cancelled":
            ical_bytes = _ical("CANCEL")
            for user in list(booking.invited_users or []):
                await _enqueue(session, booking, user, "CANCEL", ical_bytes)
            await _enqueue_organizer(
                session, booking, organizer_user, "CANCEL", ical_bytes, already_notified
            )
            await _enqueue_room_emails(session, booking, "CANCEL", ical_bytes, already_notified)

        elif action == "updated" and diff is not None:
            # When a single instance is unlinked from a series the UID
            # changes; send CANCEL for the old series UID before issuing
            # REQUEST with the new per-instance UID.
            if diff.old_series_uid:
                cancel_old = _ical_with_uid("CANCEL", diff.old_series_uid)
                cancel_notified: set[str] = set(invited_emails)
                for user in list(booking.invited_users or []):
                    await _enqueue(session, booking, user, "CANCEL", cancel_old)
                await _enqueue_organizer(
                    session, booking, organizer_user, "CANCEL", cancel_old, cancel_notified
                )
                await _enqueue_room_emails(session, booking, "CANCEL", cancel_old, set())
                req_bytes = _ical("REQUEST")
                req_notified: set[str] = set(invited_emails)
                for user in list(booking.invited_users or []):
                    await _enqueue(
                        session,
                        booking,
                        user if isinstance(user, dict) else user.model_dump(),
                        "REQUEST",
                        req_bytes,
                    )
                await _enqueue_organizer(
                    session, booking, organizer_user, "REQUEST", req_bytes, req_notified
                )
                await _enqueue_room_emails(session, booking, "REQUEST", req_bytes, req_notified)
                return

            if diff.added_users:
                ical_bytes = _ical("REQUEST")
                for invited in diff.added_users:
                    await _enqueue(session, booking, invited.model_dump(), "REQUEST", ical_bytes)

            if diff.removed_users:
                cancel_bytes = _ical("CANCEL")
                for invited in diff.removed_users:
                    await _enqueue(session, booking, invited.model_dump(), "CANCEL", cancel_bytes)

            if diff.non_participant_changed and diff.unchanged_users:
                req_bytes = _ical("REQUEST")
                for invited in diff.unchanged_users:
                    await _enqueue(session, booking, invited.model_dump(), "REQUEST", req_bytes)

            req_bytes = _ical("REQUEST")
            await _enqueue_organizer(
                session, booking, organizer_user, "REQUEST", req_bytes, already_notified
            )
            await _enqueue_room_emails(session, booking, "REQUEST", req_bytes, already_notified)

        elif action == "updated" and diff is None:
            req_bytes = _ical("REQUEST")
            await _enqueue_organizer(
                session, booking, organizer_user, "REQUEST", req_bytes, already_notified
            )
            await _enqueue_room_emails(session, booking, "REQUEST", req_bytes, already_notified)


async def _load_organizer(session: AsyncSession, booking: MeetingBooking) -> Any | None:
    """Fetch the meeting creator (organizer) from DB so we can email them.

    Returns ``None`` when the creator has been deleted (``creator_id`` is NULL
    via ``ON DELETE SET NULL``) or when the user lookup fails.
    """
    creator_id = getattr(booking, "creator_id", None)
    if creator_id is None:
        return None
    try:
        from app.models.user import User

        return await session.get(User, creator_id)
    except Exception as exc:
        logger.warning(
            "meetings.email.organizer_lookup_failed",
            error=str(exc),
            booking_id=str(booking.id),
        )
        return None


async def _enqueue_organizer(
    session: AsyncSession,
    booking: MeetingBooking,
    organizer: Any | None,
    method: str,
    ical_bytes: bytes,
    already_sent: set[str],
) -> None:
    if organizer is None:
        return
    email = (getattr(organizer, "email", "") or "").strip()
    if not email or email in already_sent:
        return
    if getattr(organizer, "notify_email", True) is False:
        return
    payload = {
        "email": email,
        "full_name": getattr(organizer, "full_name", "") or "",
    }
    await _enqueue(session, booking, payload, method, ical_bytes)
    already_sent.add(email)


async def _enqueue_room_emails(
    session: AsyncSession,
    booking: MeetingBooking,
    method: str,
    ical_bytes: bytes,
    already_sent: set[str],
) -> None:
    seen: set[str] = set()
    for br in booking.rooms:
        room = br.room
        if room is None:
            continue
        email = room.email or ""
        if not email or email in already_sent or email in seen:
            continue
        seen.add(email)
        await _enqueue(session, booking, {"email": email}, method, ical_bytes)


async def _enqueue(
    session: AsyncSession,
    booking: MeetingBooking,
    user_data: dict[str, Any],
    method: str,
    ical_bytes: bytes,
) -> None:
    from app.services.email_outbox import KIND_MEETING, encode_ical_bytes, enqueue_outbox_email

    to_email = user_data.get("email", "")
    if not to_email:
        return
    try:
        subject = _build_subject(booking, method)
        html_body = _build_html_body(booking, method)
        await enqueue_outbox_email(
            session,
            kind=KIND_MEETING,
            to_email=to_email,
            subject=subject,
            body_html=html_body,
            payload={
                "method": method,
                "ical_b64": encode_ical_bytes(ical_bytes),
            },
            related_resource_type="meeting_booking",
            related_resource_id=booking.id,
        )
    except Exception as exc:
        logger.exception(
            "meetings.email.enqueue_failed",
            error=str(exc),
            to=to_email,
            booking_id=str(booking.id),
        )


def _build_subject(booking: MeetingBooking, method: str) -> str:
    import html as _html

    title = _html.escape(booking.title)
    if method == "CANCEL":
        return f"Отменена встреча: {title}"
    return f"Приглашение на встречу: {title}"


_RU_MONTHS = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def _build_html_body(booking: MeetingBooking, method: str) -> str:
    import html as _html
    from datetime import UTC
    from zoneinfo import ZoneInfo

    from app.core.system_config import load_system_settings

    title = _html.escape(booking.title)
    desc = _html.escape(booking.description or "")
    organizer = _html.escape(booking.organizer_name)

    portal_tz = load_system_settings().timezone
    tz_info = ZoneInfo(portal_tz)

    start_utc = booking.start_time
    end_utc = booking.end_time
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=UTC)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=UTC)

    start_local = start_utc.astimezone(tz_info)
    end_local = end_utc.astimezone(tz_info)

    date_str = f"{start_local.day} {_RU_MONTHS[start_local.month]} {start_local.year}"
    time_str = f"{start_local.strftime('%H:%M')} – {end_local.strftime('%H:%M')} ({portal_tz})"

    rooms = "; ".join(br.room.name for br in booking.rooms if br.room)
    rooms_with_links = [
        (br.room.name, br.room.link) for br in booking.rooms if br.room and br.room.link
    ]

    invited_names = []
    for u in booking.invited_users or []:
        name = (
            u.get("full_name", u.get("email", ""))
            if isinstance(u, dict)
            else getattr(u, "full_name", getattr(u, "email", ""))
        )
        if name:
            invited_names.append(_html.escape(str(name)))

    if method == "CANCEL":
        header = "<h2 style='color:#c0392b;text-align:center'>Встреча отменена</h2>"
    else:
        header = "<h2 style='color:#143a66;text-align:center'>Приглашение на встречу</h2>"

    rooms_links_html = ""
    if rooms_with_links:
        links_items = "".join(
            f'<li><a href="{_html.escape(link)}">{_html.escape(name)}</a></li>'
            for name, link in rooms_with_links
        )
        rooms_links_html = f'<p><strong>Ссылки на комнаты:</strong><ul style="margin:4px 0 0 0;padding-left:20px">{links_items}</ul></p>'

    invited_html = ""
    if invited_names:
        names_items = "".join(f"<li>{name}</li>" for name in invited_names)
        invited_html = f'<p><strong>Участники:</strong><ul style="margin:4px 0 0 0;padding-left:20px">{names_items}</ul></p>'

    return f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Встреча</title></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0">
  <table width="600" align="center"
    style="background:#fff;border-radius:8px;margin:32px auto;padding:32px">
    <tr><td>
      {header}
      <p><strong>Тема:</strong> {title}</p>
      <p><strong>Организатор:</strong> {organizer}</p>
      <p><strong>Дата:</strong> {date_str}</p>
      <p><strong>Время:</strong> {time_str}</p>
      <p><strong>Комната:</strong> {_html.escape(rooms)}</p>
      {rooms_links_html}
      {invited_html}
      {f"<p><strong>Описание:</strong> {desc}</p>" if desc else ""}
    </td></tr>
  </table>
</body>
</html>"""


def _get_from_email() -> str:
    """Load portal SMTP from_address.

    Tries branding email-settings.json first (with in-process TTL cache),
    falls back to a safe default.
    """
    import json
    import time
    from pathlib import Path

    _cache = _get_from_email.__dict__
    now = time.monotonic()
    if _cache.get("value") and now - _cache.get("fetched_at", 0) < 60:
        return str(_cache["value"])

    email_file = Path("/data/branding/email-settings.json")
    result = "portal@company.local"
    if email_file.exists():
        try:
            data = json.loads(email_file.read_text("utf-8"))
            result = str(data.get("from_address") or "portal@company.local")
        except Exception as exc:
            logger.warning("meetings.email.from_address_load_failed", error=str(exc))

    _cache["value"] = result
    _cache["fetched_at"] = now
    return result
