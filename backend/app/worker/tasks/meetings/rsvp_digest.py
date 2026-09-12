"""Email-сводки RSVP для организаторов встреч.

Две cron-задачи (гейт — meetings.enabled + rsvp_ingest_enabled):

* :func:`send_rsvp_digest` — каждые 30 минут: новые/изменённые ответы с прошлого
  запуска, сгруппированные по организатору. Окно — Redis-ключ (fallback 30 мин
  при рестарте воркера: потеря одного окна при падении приемлема, дубли
  недопустимы — поэтому ключ двигается только после успешного commit outbox).
* :func:`send_rsvp_final_digest` — каждую минуту: встречи, начинающиеся через
  15 минут (жёсткое минутное окно), ещё не получившие полную сводку. Письмо —
  весь список приглашённых со статусами. Идемпотентность —
  ``meeting_bookings.rsvp_final_digest_sent_at`` (метка ставится в той же
  транзакции, что и outbox-строка: outbox-инвариант).

БД-логика вынесена в :func:`collect_digest_emails` / :func:`process_final_window`
(принимают сессию) — cron-обёртки открывают свои сессии, integration-тесты
передают savepoint-сессию.

Письма идут через общий outbox (``enqueue_outbox_email``, kind=generic); SMTP
выполняет ``process_email_outbox``. Локализация писем — русский, как у
существующих писем встреч (i18n в письмах не используется).
"""

from __future__ import annotations

import html as _html
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.meetings import MeetingBooking, MeetingRsvp
from app.models.user import User
from app.services.email_outbox import KIND_GENERIC, enqueue_outbox_email

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

DIGEST_LAST_RUN_KEY = "meetings:rsvp:digest:last_run_at"
DIGEST_WINDOW_FALLBACK = timedelta(minutes=30)

# Финальная сводка: за сколько минут до начала и ширина минутного окна
# (cron каждую минуту → каждая встреча попадает в окно ровно один раз).
FINAL_LEAD_MINUTES = 15
FINAL_WINDOW = timedelta(minutes=1)

_STATUS_LABELS_RU = {
    "accepted": "✅ Принял",
    "declined": "❌ Отклонил",
    "tentative": "⏳ Возможно",
}
_STATUS_VERBS_RU = {
    "accepted": "принял",
    "declined": "отклонил",
    "tentative": "предварительно принял",
}


def _gates_open() -> str | None:
    from app.core.modules_config import load_modules

    meetings = load_modules().meetings
    if not meetings.enabled:
        return "module_disabled"
    if not meetings.rsvp_ingest_enabled:
        return "rsvp_ingest_disabled"
    return None


def _participant_name(booking: MeetingBooking, email: str) -> str:
    for entry in booking.invited_users or []:
        if isinstance(entry, dict) and str(entry.get("email", "") or "").lower() == email:
            return str(entry.get("full_name") or email)
    return email


def _local_start_str(start: datetime, portal_tz: str, fmt: str) -> str:
    """start_time → строка в портальном часовом поясе (naive трактуем как UTC).

    ``start_time`` хранится в UTC — прямой ``strftime`` показывал бы UTC-время
    (на 3 часа раньше при МСК). Локализация — как в
    ``notifications._localized_time_and_rooms_html``.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return start.astimezone(ZoneInfo(portal_tz)).strftime(fmt)


def _wrap_html(title: str, rows: list[str]) -> str:
    items = "".join(f"<li style='margin:4px 0'>{row}</li>" for row in rows)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>{_html.escape(title)}</title></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0">
  <table width="600" align="center"
    style="background:#fff;border-radius:8px;margin:32px auto;padding:32px">
    <tr><td>
      <h2 style='color:#143a66;text-align:center'>{_html.escape(title)}</h2>
      <ul style="margin:8px 0 0 0;padding-left:20px">{items}</ul>
    </td></tr>
  </table>
</body>
</html>"""


async def _load_creators(db: AsyncSession, creator_ids: list[UUID]) -> dict[UUID, User]:
    rows = (await db.execute(select(User).where(User.id.in_(creator_ids)))).scalars().all()
    return {row.id: row for row in rows}


def _email_target(creator: User | None) -> str | None:
    """Email организатора, если ему можно слать почту (иначе None)."""
    if creator is None or not creator.email:
        return None
    if getattr(creator, "notify_email", True) is False:
        return None
    return creator.email


async def collect_digest_emails(db: AsyncSession, *, window_start: datetime, now: datetime) -> int:
    """30-мин сводка: outbox-письма организаторам по RSVP-событиям окна.

    Возвращает число созданных outbox-строк. Коммитит caller (cron-обёртка).
    """
    rsvp_rows = (
        (
            await db.execute(
                select(MeetingRsvp).where(
                    MeetingRsvp.updated_at >= window_start,
                    MeetingRsvp.updated_at < now,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rsvp_rows:
        return 0

    # Только будущие встречи: прошлым статусам организатор не нужен.
    booking_ids = {r.booking_id for r in rsvp_rows}
    bookings = (
        (
            await db.execute(
                select(MeetingBooking).where(
                    MeetingBooking.id.in_(booking_ids),
                    MeetingBooking.start_time > now,
                    MeetingBooking.creator_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    booking_map = {b.id: b for b in bookings}

    by_creator: dict[UUID, list[tuple[MeetingBooking, MeetingRsvp]]] = {}
    for rsvp in rsvp_rows:
        booking = booking_map.get(rsvp.booking_id)
        if booking is None or booking.creator_id is None:
            continue
        by_creator.setdefault(booking.creator_id, []).append((booking, rsvp))
    if not by_creator:
        return 0

    creators = await _load_creators(db, list(by_creator.keys()))
    from app.core.system_config import load_system_settings

    portal_tz = load_system_settings().timezone
    sent = 0
    for creator_id, events in by_creator.items():
        creator = creators.get(creator_id)
        to_email = _email_target(creator)
        if not to_email:
            continue
        rows = [
            "{name} — {verb} встречу «{title}» ({date})".format(
                name=_html.escape(_participant_name(booking, rsvp.participant_email)),
                verb=_STATUS_VERBS_RU[rsvp.status],
                title=_html.escape(booking.title),
                date=_local_start_str(booking.start_time, portal_tz, "%d.%m %H:%M"),
            )
            for booking, rsvp in events
        ]
        await enqueue_outbox_email(
            db,
            kind=KIND_GENERIC,
            to_email=to_email,
            subject=f"Ответы на приглашения: {len(events)} событий",
            body_html=_wrap_html("Кто ответил на ваши приглашения", rows),
            payload={"smtp_source": "meetings_rsvp_digest"},
            related_resource_type="meeting_booking",
            related_resource_id=events[0][0].id,
        )
        sent += 1
    return sent


async def process_final_window(db: AsyncSession, *, now: datetime) -> int:
    """Финальная сводка: письма по встречам в окне [now+15m, now+16m).

    Метка ``rsvp_final_digest_sent_at`` ставится в той же транзакции, что и
    outbox-строка (outbox-инвариант); в т.ч. без письма (notify_email=False /
    нет создателя) — иначе встреча попадала бы в окно повторно.
    """
    window_from = now + timedelta(minutes=FINAL_LEAD_MINUTES)
    window_to = window_from + FINAL_WINDOW

    bookings = (
        (
            await db.execute(
                select(MeetingBooking).where(
                    MeetingBooking.start_time >= window_from,
                    MeetingBooking.start_time < window_to,
                    MeetingBooking.rsvp_final_digest_sent_at.is_(None),
                    MeetingBooking.creator_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not bookings:
        return 0

    creators = await _load_creators(db, [b.creator_id for b in bookings if b.creator_id])
    from app.core.system_config import load_system_settings

    portal_tz = load_system_settings().timezone
    sent = 0
    for booking in bookings:
        booking.rsvp_final_digest_sent_at = now
        creator = creators.get(booking.creator_id) if booking.creator_id else None
        to_email = _email_target(creator)
        if not to_email:
            continue

        rsvp_rows = (
            (await db.execute(select(MeetingRsvp).where(MeetingRsvp.booking_id == booking.id)))
            .scalars()
            .all()
        )
        rsvp_by_email = {r.participant_email.lower(): r for r in rsvp_rows}

        rows: list[str] = []
        for entry in booking.invited_users or []:
            if not isinstance(entry, dict):
                continue
            email = str(entry.get("email", "") or "").lower()
            if not email:
                continue
            name = _html.escape(str(entry.get("full_name") or email))
            rsvp = rsvp_by_email.get(email)
            label = _STATUS_LABELS_RU[rsvp.status] if rsvp else "⚪ Не ответил"
            rows.append(f"{name} — {label}")

        header = (
            f"Встреча «{_html.escape(booking.title)}» — "
            f"{_local_start_str(booking.start_time, portal_tz, '%H:%M')}"
        )
        await enqueue_outbox_email(
            db,
            kind=KIND_GENERIC,
            to_email=to_email,
            subject=f"Встреча «{booking.title}» через 15 минут: список участников",
            body_html=_wrap_html(header, rows),
            payload={"smtp_source": "meetings_rsvp_final"},
            related_resource_type="meeting_booking",
            related_resource_id=booking.id,
        )
        sent += 1
    return sent


async def send_rsvp_digest(ctx: dict) -> dict:
    """Cron-обёртка 30-мин сводки: гейты + окно из Redis + своя транзакция."""
    redis: Redis | None = ctx.get("redis")
    if redis is None:
        return {"skipped": "no_redis"}
    reason = _gates_open()
    if reason is not None:
        return {"skipped": reason}

    now = datetime.now(UTC)
    window_start = now - DIGEST_WINDOW_FALLBACK
    raw_last = await redis.get(DIGEST_LAST_RUN_KEY)
    if raw_last:
        if isinstance(raw_last, bytes):
            raw_last = raw_last.decode("utf-8", errors="ignore")
        try:
            parsed_last = datetime.fromisoformat(str(raw_last))
            if parsed_last.tzinfo is None:
                parsed_last = parsed_last.replace(tzinfo=UTC)
            window_start = parsed_last
        except ValueError:
            pass  # битое значение — fallback-окно

    async with AsyncSessionLocal() as db, db.begin():
        sent = await collect_digest_emails(db, window_start=window_start, now=now)

    # Двигаем окно только после успешного commit outbox-строк.
    await redis.set(DIGEST_LAST_RUN_KEY, now.isoformat())
    logger.info("meetings.rsvp.digest_sent", emails=sent)
    return {"sent": sent}


async def send_rsvp_final_digest(ctx: dict) -> dict:
    """Cron-обёртка финальной сводки: гейты + своя транзакция."""
    reason = _gates_open()
    if reason is not None:
        return {"skipped": reason}

    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db, db.begin():
        sent = await process_final_window(db, now=now)

    logger.info("meetings.rsvp.final_digest_sent", emails=sent)
    return {"sent": sent}
