from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from app.core.logging import get_logger
from app.services.email_outbox import OutboxItem

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.meetings import MeetingBooking
    from app.services.meetings.bookings_service import BookingDiff

    IcalFn = Callable[[Literal["REQUEST", "CANCEL"]], bytes]
    IcalUidFn = Callable[[Literal["REQUEST", "CANCEL"], str], bytes]

logger = get_logger(__name__)


def _resolve_company_domain() -> str:
    """Derive the bare hostname from the configured portal base URL."""
    from urllib.parse import urlparse

    from app.core.system_config import load_system_settings

    raw_url = getattr(load_system_settings(), "portal_base_url", "portal.company.local")
    parsed_url = urlparse(raw_url if "://" in raw_url else f"//{raw_url}")
    return parsed_url.hostname or raw_url


def _collect_invited_emails(booking: MeetingBooking) -> set[str]:
    """Non-empty e-mail set of all invited users (dict or model)."""
    invited_emails: set[str] = {
        u.get("email", "") if isinstance(u, dict) else getattr(u, "email", "")
        for u in (booking.invited_users or [])
    }
    invited_emails.discard("")
    return invited_emails


async def _enqueue_all_recipients(
    session: AsyncSession,
    booking: MeetingBooking,
    organizer_user: Any | None,
    method: Literal["REQUEST", "CANCEL"],
    ical: IcalFn,
    already_notified: set[str],
    absences_by_email: dict[str, Any],
) -> None:
    """Send *method* to every invited user, the organizer and the rooms."""
    ical_bytes = ical(method)
    # Batch: один INSERT на всех invited вместо N round-trip (audit M3).
    invited_emails = [
        (u.get("email", "") if isinstance(u, dict) else getattr(u, "email", "")) or ""
        for u in (booking.invited_users or [])
    ]
    await _enqueue_many(session, booking, invited_emails, method, ical_bytes, absences_by_email)
    await _enqueue_organizer(
        session, booking, organizer_user, method, ical_bytes, already_notified, absences_by_email
    )
    await _enqueue_room_emails(
        session, booking, method, ical_bytes, already_notified, absences_by_email
    )


async def _enqueue_organizer_and_rooms(
    session: AsyncSession,
    booking: MeetingBooking,
    organizer_user: Any | None,
    ical: IcalFn,
    already_notified: set[str],
    absences_by_email: dict[str, Any],
) -> None:
    """Send a REQUEST to the organizer and rooms (not the invited list)."""
    req_bytes = ical("REQUEST")
    await _enqueue_organizer(
        session, booking, organizer_user, "REQUEST", req_bytes, already_notified, absences_by_email
    )
    await _enqueue_room_emails(
        session, booking, "REQUEST", req_bytes, already_notified, absences_by_email
    )


async def _enqueue_series_relink(
    session: AsyncSession,
    booking: MeetingBooking,
    organizer_user: Any | None,
    old_series_uid: str,
    invited_emails: set[str],
    ical: IcalFn,
    ical_with_uid: IcalUidFn,
    absences_by_email: dict[str, Any],
) -> None:
    """Unlink-from-series flow: CANCEL the old series UID, then REQUEST the new one.

    When a single instance is unlinked from a series the UID changes; send
    CANCEL for the old series UID before issuing REQUEST with the new
    per-instance UID.
    """
    cancel_old = ical_with_uid("CANCEL", old_series_uid)
    cancel_notified: set[str] = set(invited_emails)
    # Batch CANCEL для всех invited одним INSERT (audit M3).
    await _enqueue_many(
        session, booking, list(invited_emails), "CANCEL", cancel_old, absences_by_email
    )
    await _enqueue_organizer(
        session, booking, organizer_user, "CANCEL", cancel_old, cancel_notified, absences_by_email
    )
    await _enqueue_room_emails(session, booking, "CANCEL", cancel_old, set(), absences_by_email)

    req_bytes = ical("REQUEST")
    req_notified: set[str] = set(invited_emails)
    # Batch REQUEST для всех invited одним INSERT (audit M3).
    await _enqueue_many(
        session, booking, list(invited_emails), "REQUEST", req_bytes, absences_by_email
    )
    await _enqueue_organizer(
        session, booking, organizer_user, "REQUEST", req_bytes, req_notified, absences_by_email
    )
    await _enqueue_room_emails(
        session, booking, "REQUEST", req_bytes, req_notified, absences_by_email
    )


async def _enqueue_updated_with_diff(
    session: AsyncSession,
    booking: MeetingBooking,
    organizer_user: Any | None,
    diff: BookingDiff,
    invited_emails: set[str],
    already_notified: set[str],
    ical: IcalFn,
    ical_with_uid: IcalUidFn,
    absences_by_email: dict[str, Any],
) -> None:
    """Differential update: notify added/removed/unchanged users + organizer/rooms."""
    if diff.old_series_uid:
        await _enqueue_series_relink(
            session,
            booking,
            organizer_user,
            diff.old_series_uid,
            invited_emails,
            ical,
            ical_with_uid,
            absences_by_email,
        )
        return

    if diff.added_users:
        ical_bytes = ical("REQUEST")
        # Batch: один INSERT на всех добавленных (audit M3).
        added_emails = [getattr(invited, "email", "") or "" for invited in diff.added_users]
        await _enqueue_many(
            session, booking, added_emails, "REQUEST", ical_bytes, absences_by_email
        )

    if diff.removed_users:
        cancel_bytes = ical("CANCEL")
        removed_emails = [getattr(invited, "email", "") or "" for invited in diff.removed_users]
        await _enqueue_many(
            session, booking, removed_emails, "CANCEL", cancel_bytes, absences_by_email
        )

    if diff.non_participant_changed and diff.unchanged_users:
        req_bytes = ical("REQUEST")
        unchanged_emails = [getattr(invited, "email", "") or "" for invited in diff.unchanged_users]
        await _enqueue_many(
            session, booking, unchanged_emails, "REQUEST", req_bytes, absences_by_email
        )

    await _enqueue_organizer_and_rooms(
        session, booking, organizer_user, ical, already_notified, absences_by_email
    )


async def enqueue_meeting_emails(
    session: AsyncSession,
    *,
    booking: MeetingBooking,
    action: Literal["created", "updated", "cancelled"],
    diff: BookingDiff | None = None,
) -> None:
    """Записывает в email_outbox по строке на каждого получателя в *переданной*
    сессии.

    Outbox-инвариант: письма коммитятся в той же транзакции, что и бизнес-
    операция (бронирование). Эта функция НЕ открывает свою сессию и НЕ
    коммитит — за commit отвечает caller (роут, который создаёт/меняет
    бронирование). iCal строится максимум дважды (REQUEST/CANCEL); сам SMTP
    выполняет cron-воркер (app.worker.tasks.email_outbox.process_email_outbox).
    """
    from app.services.meetings.ical_builder import build_ical

    company_domain = _resolve_company_domain()
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

    invited_emails = _collect_invited_emails(booking)
    organizer_user = await _load_organizer(session, booking)
    already_notified: set[str] = set(invited_emails)

    # Enrich отсутствий один раз на дату встречи. HTML письма общий для всех
    # получателей — подпись относится к участникам из списка, не к адресату.
    from app.services.meetings.absence_enrichment import enrich_absences_for_invited

    absences_by_email = await enrich_absences_for_invited(
        session, booking.invited_users or [], on_date=booking.start_time.date()
    )

    if action == "created":
        await _enqueue_all_recipients(
            session, booking, organizer_user, "REQUEST", _ical, already_notified, absences_by_email
        )
    elif action == "cancelled":
        await _enqueue_all_recipients(
            session, booking, organizer_user, "CANCEL", _ical, already_notified, absences_by_email
        )
    elif action == "updated" and diff is not None:
        await _enqueue_updated_with_diff(
            session,
            booking,
            organizer_user,
            diff,
            invited_emails,
            already_notified,
            _ical,
            _ical_with_uid,
            absences_by_email,
        )
    elif action == "updated" and diff is None:
        await _enqueue_organizer_and_rooms(
            session, booking, organizer_user, _ical, already_notified, absences_by_email
        )


async def dispatch_meeting_emails(
    *,
    booking: MeetingBooking,
    action: Literal["created", "updated", "cancelled"],
    diff: BookingDiff | None = None,
) -> None:
    """Standalone-обёртка (legacy / ARQ-fallback): открывает собственную
    сессию + транзакцию и делегирует в :func:`enqueue_meeting_emails`.

    В обычном потоке роуты вызывают ``enqueue_meeting_emails`` напрямую с той
    же сессией, что и бронирование, чтобы письма коммитились атомарно.
    """
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session, session.begin():
        await enqueue_meeting_emails(session, booking=booking, action=action, diff=diff)


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
    absences_by_email: dict[str, Any],
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
    await _enqueue(session, booking, payload, method, ical_bytes, absences_by_email)
    already_sent.add(email)


async def _enqueue_room_emails(
    session: AsyncSession,
    booking: MeetingBooking,
    method: str,
    ical_bytes: bytes,
    already_sent: set[str],
    absences_by_email: dict[str, Any],
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
        # Комнаты — не сотрудники, отсутствие к ним не относится; HTML общий
        # для всех получателей, поэтому подпись absence в письме комнаты та же.
        await _enqueue(session, booking, {"email": email}, method, ical_bytes, absences_by_email)


async def _enqueue(
    session: AsyncSession,
    booking: MeetingBooking,
    user_data: dict[str, Any],
    method: str,
    ical_bytes: bytes,
    absences_by_email: dict[str, Any],
) -> None:
    from app.services.email_outbox import KIND_MEETING, encode_ical_bytes, enqueue_outbox_email

    to_email = user_data.get("email", "")
    if not to_email:
        return
    try:
        subject = _build_subject(booking, method)
        html_body = _build_html_body(booking, method, absences_by_email)
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


def _build_outbox_item(
    booking: MeetingBooking,
    to_email: str,
    method: str,
    subject: str,
    html_body: str,
    ical_bytes: bytes,
) -> OutboxItem | None:
    """Build one outbox item; returns None if email is empty (skip).

    subject/html_body передаются уже построенными — для batch'а они считаются
    один раз на method (они зависят только от booking+method, не от получателя).
    """
    if not to_email:
        return None
    from app.services.email_outbox import KIND_MEETING, encode_ical_bytes

    return OutboxItem(
        kind=KIND_MEETING,
        to_email=to_email,
        subject=subject,
        body_html=html_body,
        payload={"method": method, "ical_b64": encode_ical_bytes(ical_bytes)},
        related_resource_type="meeting_booking",
        related_resource_id=booking.id,
    )


async def _enqueue_many(
    session: AsyncSession,
    booking: MeetingBooking,
    emails: list[str],
    method: str,
    ical_bytes: bytes,
    absences_by_email: dict[str, Any],
) -> None:
    """Batch-INSERT нескольких получателей одним запросом (audit M3).

    Заменяет цикл ``for user in invited: await _enqueue(...)`` (N round-trip)
    одним multi-row INSERT. subject/html_body строятся один раз — они одинаковы
    для всех получателей одного method. Пустые/дубли emails пропускаются
    (семантика прежнего цикла). Ошибки логируются на уровне batch'а (как и в
    ``_enqueue``), транзакция не прерывается — caller сам решает commit.
    """
    if not emails:
        return
    # Дедупликация с сохранением порядка (раньше дубли могли попасть в INSERT,
    # но приводили к нескольким письмам — см. characterization-тесты на дедуп).
    seen: set[str] = set()
    unique_emails: list[str] = []
    for email in emails:
        if email and email not in seen:
            seen.add(email)
            unique_emails.append(email)
    if not unique_emails:
        return
    try:
        from app.services.email_outbox import enqueue_outbox_email_batch

        subject = _build_subject(booking, method)
        html_body = _build_html_body(booking, method, absences_by_email)
        items = [
            item
            for item in (
                _build_outbox_item(booking, email, method, subject, html_body, ical_bytes)
                for email in unique_emails
            )
            if item is not None
        ]
        if items:
            await enqueue_outbox_email_batch(session, items)
    except Exception as exc:
        logger.exception(
            "meetings.email.enqueue_batch_failed",
            error=str(exc),
            recipients=len(unique_emails),
            booking_id=str(booking.id),
        )


def _build_subject(booking: MeetingBooking, method: str) -> str:
    title = booking.title
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


def _build_html_body(
    booking: MeetingBooking,
    method: str,
    absences_by_email: dict[str, Any] | None = None,
) -> str:
    import html as _html

    title = _html.escape(booking.title)
    desc = _html.escape(booking.description or "")
    organizer = _html.escape(booking.organizer_name)
    header = _header_html(method)
    date_str, time_str, rooms_str = _localized_time_and_rooms_html(booking)
    rooms_links_html = _rooms_links_html(booking)
    invited_html = _invited_html(booking, absences_by_email or {})
    desc_html = f"<p><strong>Описание:</strong> {desc}</p>" if desc else ""

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
      <p><strong>Комната:</strong> {rooms_str}</p>
      {rooms_links_html}
      {invited_html}
      {desc_html}
    </td></tr>
  </table>
</body>
</html>"""


def _header_html(method: str) -> str:
    """Цветной заголовок письма: красный для отмены, синий для приглашения."""
    if method == "CANCEL":
        return "<h2 style='color:#c0392b;text-align:center'>Встреча отменена</h2>"
    return "<h2 style='color:#143a66;text-align:center'>Приглашение на встречу</h2>"


def _localized_time_and_rooms_html(booking: MeetingBooking) -> tuple[str, str, str]:
    """Дата/время в часовом поясе портала + строка имён комнат (HTML-escape).

    Возвращает кортеж (date_str, time_str, rooms_str) для подстановки в шаблон
    письма. naive-даты трактуются как UTC (защита от записей без tz).
    """
    import html as _html
    from datetime import UTC
    from zoneinfo import ZoneInfo

    from app.core.system_config import load_system_settings

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
    return date_str, time_str, _html.escape(rooms)


def _rooms_links_html(booking: MeetingBooking) -> str:
    """Блок «Ссылки на комнаты» для комнат с заполненным link (пусто если нет)."""
    import html as _html

    links = [(br.room.name, br.room.link) for br in booking.rooms if br.room and br.room.link]
    if not links:
        return ""
    items = "".join(
        f'<li><a href="{_html.escape(link)}">{_html.escape(name)}</a></li>' for name, link in links
    )
    return f'<p><strong>Ссылки на комнаты:</strong><ul style="margin:4px 0 0 0;padding-left:20px">{items}</ul></p>'


def _invited_html(booking: MeetingBooking, absences_by_email: dict[str, Any]) -> str:
    """Блок «Участники» с информационной подписью отсутствия.

    Подпись absence (отпуск/болезнь/командировка) добавляется под именем для тех,
    у кого отсутствие действует на дату встречи. HTML письма общий для всех
    получателей — подпись относится к участнику из списка, а не к адресату.
    Пусто, если участников нет.
    """
    import html as _html

    items: list[str] = []
    for u in booking.invited_users or []:
        name = _invited_name(u)
        if not name:
            continue
        email_raw = _invited_email(u)
        note_html = ""
        if email_raw:
            absence = absences_by_email.get(str(email_raw).lower())
            if absence is not None:
                note_html = _absence_note_html(absence)
        items.append(f"<li>{_html.escape(str(name))}{note_html}</li>")
    if not items:
        return ""
    names = "".join(items)
    return f'<p><strong>Участники:</strong><ul style="margin:4px 0 0 0;padding-left:20px">{names}</ul></p>'


def _invited_name(u: Any) -> str:
    """Имя участника из dict (JSONB) или InvitedUser (fallback на email)."""
    if isinstance(u, dict):
        return str(u.get("full_name") or u.get("email") or "")
    return str(getattr(u, "full_name", "") or getattr(u, "email", "") or "")


def _invited_email(u: Any) -> str:
    """Email участника из dict (JSONB) или InvitedUser (для lookup absence)."""
    if isinstance(u, dict):
        return str(u.get("email") or "")
    return str(getattr(u, "email", "") or "")


# Русские подписи категорий отсутствия для письма (i18n в письме не
# используется — как и существующий хардкод темы «Приглашение на встречу»).
_PRESENCE_LABELS_RU: dict[str, str] = {
    "vacation": "В отпуске",
    "sick": "Болеет",
    "business_trip": "В командировке",
}

# Цвета подписи по категории (как CSS-классы в StaffRow.vue / ParticipantPicker).
_PRESENCE_COLORS: dict[str, str] = {
    "vacation": "#b45309",  # amber
    "sick": "#be123c",  # red
    "business_trip": "#6d28d9",  # purple
}


def _absence_note_html(absence: Any) -> str:
    """Информационная подпись отсутствия под именем участника (HTML, цветная).

    Формат: «В отпуске · до 15 августа» — мелким цветным текстом. Дата берётся из
    ``absence.end_date`` (когда отсутствие заканчивается). HTML-экранирование
    даты не нужно — она формируется из чисел и словаря русских месяцев.
    """
    category = getattr(absence, "category", "")
    label = _PRESENCE_LABELS_RU.get(category, "")
    if not label:
        return ""
    color = _PRESENCE_COLORS.get(category, "#6b7280")
    end = getattr(absence, "end_date", None)
    prefix = f'<div style="font-size:11px;color:{color};margin-top:2px">'
    if end is not None:
        until_str = f"{end.day} {_RU_MONTHS.get(end.month, '')}"
        return f"{prefix}{_html_escape(label)} · до {_html_escape(until_str)}</div>"
    return f"{prefix}{_html_escape(label)}</div>"


def _html_escape(s: str) -> str:
    import html as _html

    return _html.escape(s)


def _get_from_email() -> str:
    """Load portal SMTP from_address via the shared email-settings loader.

    Uses an in-process TTL cache, falls back to a safe default.
    """
    import time

    from app.services.email_settings import read_email_settings

    _cache = _get_from_email.__dict__
    now = time.monotonic()
    if _cache.get("value") and now - _cache.get("fetched_at", 0) < 60:
        return str(_cache["value"])

    settings = read_email_settings()
    result = (settings.from_address if settings else "") or "portal@company.local"

    _cache["value"] = result
    _cache["fetched_at"] = now
    return result
