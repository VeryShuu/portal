"""RSVP-инджест: приём IMIP-ответов из общего ящика портала в БД встреч.

Два слоя:

* IMAP-транспорт (:func:`fetch_reply_candidates` / :func:`delete_reply_messages`)
  — клон паттерна ``app/services/erp_sync/mailbox.py``: общий ящик
  (portal@, его читают люди, параллельно поллится ERP-синк) → ``SEARCH ALL``,
  ``\\Seen`` не ставим, «обработано» = дедуп по ``Message-ID`` в БД,
  чужие письма не трогаем. Отличие фильтра: ERP матчит по темам, мы — по
  наличию валидного календарного REPLY (:mod:`rsvp_parser`).
* Инджест (:func:`apply_reply`) — матчинг UID → встреча/серия, upsert
  статуса, подготовка данных для уведомлений. НЕ коммитит: транзакцию
  открывает worker (outbox-инвариант — как у enqueue_meeting_emails).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.meetings import (
    MeetingBooking,
    MeetingBookingRoom,
    MeetingRsvp,
    MeetingRsvpEmailLog,
)
from app.schemas.branding import EmailSettings
from app.schemas.meetings import RsvpInfo
from app.services.meetings.rsvp_parser import ParsedReply, parse_reply_email, parse_uid

logger = get_logger(__name__)

RsvpStatus = Literal["accepted", "declined", "tentative"]

# Redis-ключи worker-обёртки (клон конвенции helpdesk/erp_sync).
RSVP_LAST_POLL_KEY = "meetings:rsvp:last_poll_at"
RSVP_POLL_LOCK_KEY = "meetings:rsvp:poll_lock"
RSVP_POLL_LOCK_TTL = 120  # 2 мин: батч писем × IMAP-таймауты.
RSVP_POLL_INTERVAL_SECONDS = 60  # реальный интервал (cron дёргает чаще).

_LITERAL_RE = re.compile(rb"\{\d+\}")
_IMAP_STEP_TIMEOUT = 15.0

# Русские формы статусов для in-app уведомления организатору.
STATUS_VERBS_RU = {
    "accepted": "принял приглашение",
    "declined": "отклонил приглашение",
    "tentative": "предварительно принял приглашение",
}


@dataclass(slots=True)
class RsvpChange:
    """Изменение статуса по одной встрече — данные для уведомления создателю."""

    booking_id: UUID
    creator_id: UUID | None
    booking_title: str
    date_str: str  # UTC-дата, как у publish_meeting_event в роутах
    room_ids: list[UUID] = field(default_factory=list)
    participant_name: str = ""
    status: str = ""


@dataclass(slots=True)
class IngestOutcome:
    """Результат обработки одного письма (для метрик поллера)."""

    status: str  # applied | duplicate | not_found | not_invited | ignored
    changes: list[RsvpChange] = field(default_factory=list)


def _fallback_message_id(raw: bytes) -> str:
    """Синтетический Message-ID для писем без него (крайне редки, но без
    этого дедуп невозможен и письмо парсилось бы каждый poll)."""
    return f"<rsvp-{hashlib.sha1(raw).hexdigest()}@portal.local>"


def _as_utc(value: datetime, portal_tz: str) -> datetime:
    """RECURRENCE-ID → aware-UTC (naive-значение трактуем как портанный TZ)."""
    if value.tzinfo is None:
        from zoneinfo import ZoneInfo

        return value.replace(tzinfo=ZoneInfo(portal_tz)).astimezone(UTC)
    return value.astimezone(UTC)


def _invited_entry(booking: MeetingBooking, email: str) -> dict[str, Any] | None:
    """Элемент ``invited_users`` для участника (CI-матч по email) или None."""
    for entry in booking.invited_users or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("email", "") or "").strip().lower() == email:
            return entry
    return None


def _participant_user_id(entry: dict[str, Any]) -> UUID | None:
    """user_id приглашённого → UUID (внешние участники ``ext:<email>`` → None)."""
    raw = str(entry.get("user_id", "") or "")
    if not raw or raw.startswith("ext:"):
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


async def _load_bookings_for_reply(
    db: AsyncSession, parsed: ParsedReply, now: datetime
) -> list[MeetingBooking] | None:
    """Встречи, к которым применяется ответ. ``None`` = встреча не найдена.

    * UID одиночной встречи → она сама (RECURRENCE-ID игнорируем).
    * UID серии + RECURRENCE-ID → конкретный экземпляр (матч по start_time UTC).
    * UID серии без RECURRENCE-ID («ответил на всю серию») → все будущие
      экземпляры (start_time >= now): прошедшие статусы неинтересны.
    """
    parsed_uid = parse_uid(parsed.uid)
    if parsed_uid is None:
        return None

    if parsed_uid.booking_id is not None:
        booking = await db.get(MeetingBooking, parsed_uid.booking_id)
        return [booking] if booking is not None else None

    # Серия.
    stmt = select(MeetingBooking).where(MeetingBooking.series_id == parsed_uid.series_id)
    if parsed.recurrence_id is not None:
        from app.core.system_config import load_system_settings

        target = _as_utc(parsed.recurrence_id, load_system_settings().timezone)
        stmt = stmt.where(MeetingBooking.start_time == target)
    else:
        stmt = stmt.where(MeetingBooking.start_time >= now).order_by(MeetingBooking.start_time)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows) if rows else None


async def apply_reply(db: AsyncSession, parsed: ParsedReply, message_id: str) -> IngestOutcome:
    """Записать статус из REPLY. Не коммитит (транзакция — у worker-обёртки).

    Дедуп: ``message_id`` уже в ``meeting_rsvp_email_log`` → ``duplicate``
    (письмо удаляем, но ничего не меняем). Лог пишется при любом исходе,
    кроме битого парса — чтобы не перекладывать одно и то же письмо.
    """
    existing_log = await db.get(MeetingRsvpEmailLog, message_id)
    if existing_log is not None:
        return IngestOutcome(status="duplicate")

    now = datetime.now(UTC)
    bookings = await _load_bookings_for_reply(db, parsed, now)
    if bookings is None:
        await _write_log(db, message_id)
        return IngestOutcome(status="not_found")

    room_ids_map = await _room_ids_map(db, [b.id for b in bookings])
    # FK-защита: user_id в JSONB-слепке может протухнуть (сотрудник удалён из
    # Directory после приглашения) — валидируем одним bulk-запросом, несуществующие → NULL.
    candidate_uids = {
        uid
        for b in bookings
        if (entry := _invited_entry(b, parsed.attendee_email)) is not None
        and (uid := _participant_user_id(entry)) is not None
    }
    existing_uids = await _existing_user_ids(db, candidate_uids)
    outcome = IngestOutcome(status="ignored")
    any_invited = False

    for booking in bookings:
        entry = _invited_entry(booking, parsed.attendee_email)
        if entry is None:
            continue  # участник не приглашён на этот экземпляр — skip
        any_invited = True

        candidate = _participant_user_id(entry)
        user_id = candidate if candidate in existing_uids else None
        prev = await _current_status(db, booking.id, parsed.attendee_email)
        if prev == parsed.status:
            continue  # статус не изменился — уведомлять незачем

        stmt = (
            pg_insert(MeetingRsvp)
            .values(
                booking_id=booking.id,
                participant_email=parsed.attendee_email,
                participant_user_id=user_id,
                status=parsed.status,
                source="email",
            )
            .on_conflict_do_update(
                constraint="uq_meeting_rsvp_booking_participant",
                set_={
                    "status": parsed.status,
                    "participant_user_id": user_id,
                    "source": "email",
                },
            )
        )
        await db.execute(stmt)

        outcome.changes.append(
            RsvpChange(
                booking_id=booking.id,
                creator_id=booking.creator_id,
                booking_title=booking.title,
                date_str=booking.start_time.date().isoformat(),
                room_ids=room_ids_map.get(booking.id, []),
                participant_name=str(entry.get("full_name") or parsed.attendee_email),
                status=parsed.status,
            )
        )

    outcome.status = (
        "applied" if outcome.changes else ("not_invited" if not any_invited else "ignored")
    )
    await _write_log(db, message_id)
    return outcome


async def _current_status(db: AsyncSession, booking_id: UUID, email: str) -> str | None:
    stmt = select(MeetingRsvp.status).where(
        MeetingRsvp.booking_id == booking_id, MeetingRsvp.participant_email == email
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _room_ids_map(db: AsyncSession, booking_ids: list[UUID]) -> dict[UUID, list[UUID]]:
    """room_ids по встречам — прямым SELECT (вне async-lazy relationship)."""
    if not booking_ids:
        return {}
    stmt = select(MeetingBookingRoom.booking_id, MeetingBookingRoom.room_id).where(
        MeetingBookingRoom.booking_id.in_(booking_ids)
    )
    result: dict[UUID, list[UUID]] = {}
    for booking_id, room_id in (await db.execute(stmt)).all():
        result.setdefault(booking_id, []).append(room_id)
    return result


async def _existing_user_ids(db: AsyncSession, user_ids: set[UUID]) -> set[UUID]:
    """Подмножество id, реально существующих в ``users`` (FK-защита)."""
    if not user_ids:
        return set()
    from app.models.user import User

    rows = await db.execute(select(User.id).where(User.id.in_(user_ids)))
    return {row for row in rows.scalars()}


async def _write_log(db: AsyncSession, message_id: str) -> None:
    db.add(MeetingRsvpEmailLog(message_id=message_id))


async def load_rsvp_map(
    db: AsyncSession, booking_ids: list[UUID]
) -> dict[UUID, dict[str, RsvpInfo]]:
    """RSVP-статусы для списка встреч: ``{booking_id: {email_lower: RsvpInfo}}``.

    Bulk-запрос одним IN — для enrich ``BookingOut.invited_users[].rsvp``
    (паттерн absence_enrichment: один запрос на список встреч, не N+1).
    """
    if not booking_ids:
        return {}
    stmt = select(MeetingRsvp).where(MeetingRsvp.booking_id.in_(booking_ids))
    result: dict[UUID, dict[str, RsvpInfo]] = {}
    for row in (await db.execute(stmt)).scalars():
        # CHECK ck_meeting_rsvp_status гарантирует тройку значений схемы
        status = cast(RsvpStatus, row.status)
        result.setdefault(row.booking_id, {})[row.participant_email.lower()] = RsvpInfo(
            status=status, updated_at=row.updated_at
        )
    return result


# ── IMAP-транспорт (клон erp_sync/mailbox, фильтр — по IMIP REPLY) ─────────


def _make_imap_client(settings: EmailSettings) -> Any:
    import aioimaplib

    if settings.imap_use_ssl:
        return aioimaplib.IMAP4_SSL(host=settings.imap_host, port=settings.imap_port)
    return aioimaplib.IMAP4(host=settings.imap_host, port=settings.imap_port)


async def _imap_step(coro: Any, *, what: str = "") -> Any:
    """Таймаут-обёртка: зависшая IMAP-команда не должна вешать воркер (см.
    erp_sync/mailbox._IMAP_STEP_TIMEOUT — реальная грабля с firewall)."""
    import asyncio

    return await asyncio.wait_for(coro, timeout=_IMAP_STEP_TIMEOUT)


async def _search_all(client: Any) -> list[str]:
    """``SEARCH ALL`` (не UNSEEN!): ящик общий, люди читают его руками —
    «обработано» определяется дедупом по Message-ID, а не флагом \\Seen."""
    typ, data = await _imap_step(client.search("ALL"), what="search")
    if typ != "OK" or not data or not data[0]:
        return []
    raw = data[0]
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="ignore")
    return [u for u in raw.split() if u]


def _extract_rfc822(data: Any) -> bytes | None:
    """RFC822 из плоского aioimaplib-ответа (literal-маркер ``{NNN}`` + тело)."""
    items = list(data)
    for index, item in enumerate(items):
        if (
            isinstance(item, (bytes, bytearray))
            and _LITERAL_RE.search(bytes(item))
            and index + 1 < len(items)
            and isinstance(items[index + 1], (bytes, bytearray))
        ):
            return bytes(items[index + 1])
    for item in items:
        if isinstance(item, tuple):
            for part in item:
                if isinstance(part, (bytes, bytearray)) and not _LITERAL_RE.search(bytes(part)):
                    return bytes(part)
    return None


@dataclass(slots=True)
class ReplyCandidate:
    """Валидный REPLY из ящика: IMAP-UID, распарсенные данные, сырые байты."""

    uid: str
    parsed: ParsedReply
    raw: bytes

    @property
    def message_id(self) -> str:
        return self.parsed.message_id or _fallback_message_id(self.raw)


async def fetch_reply_candidates(settings: EmailSettings) -> list[ReplyCandidate]:
    """Все валидные IMIP-REPLY из общего ящика.

    Письма без календарного REPLY не возвращаются и никак не меняются в
    ящике (их может забрать ERP-поллер или прочитать человек).
    """
    password = settings.imap_password
    if not password:
        logger.warning("meetings.rsvp.no_password")
        return []

    client = _make_imap_client(settings)
    results: list[ReplyCandidate] = []
    try:
        await _imap_step(client.wait_hello_from_server(), what="hello")
        await _imap_step(client.login(settings.imap_username, password), what="login")
        await _imap_step(client.select(settings.imap_folder), what="select")

        for uid in await _search_all(client):
            try:
                typ, data = await _imap_step(client.fetch(uid, "(RFC822)"), what="fetch")
                if typ != "OK":
                    continue
                raw = _extract_rfc822(data)
                if raw is None:
                    continue
                parsed = parse_reply_email(raw)
                if parsed is not None:
                    results.append(ReplyCandidate(uid=uid, parsed=parsed, raw=raw))
            except Exception:
                logger.exception("meetings.rsvp.uid_fetch_failed", uid=uid)
    finally:
        try:
            await client.logout()
        except Exception:
            logger.warning("meetings.rsvp.logout_failed", exc_info=True)

    logger.info("meetings.rsvp.fetch_done", candidates=len(results))
    return results


async def delete_reply_messages(settings: EmailSettings, uids: list[str]) -> int:
    """Удалить обработанные REPLY (``STORE \\Deleted`` + ``EXPUNGE``).

    Отдельное подключение: fetch-сессия уже закрыта. Best-effort: неудалённое
    письмо останется в ящике, дедуп по message_id удержит повторную обработку.
    """
    if not uids:
        return 0
    password = settings.imap_password
    if not password:
        return 0

    deleted = 0
    client = _make_imap_client(settings)
    try:
        await _imap_step(client.wait_hello_from_server(), what="hello")
        await _imap_step(client.login(settings.imap_username, password), what="login")
        await _imap_step(client.select(settings.imap_folder), what="select")
        for uid in uids:
            try:
                await _imap_step(client.store(uid, "+FLAGS", "\\Deleted"), what="store")
                deleted += 1
            except Exception:
                logger.warning("meetings.rsvp.mark_deleted_failed", uid=uid, exc_info=True)
        try:
            await _imap_step(client.expunge(), what="expunge")
        except Exception:
            logger.debug("meetings.rsvp.expunge_failed", exc_info=True)
    finally:
        try:
            await client.logout()
        except Exception:
            logger.warning("meetings.rsvp.delete_logout_failed", exc_info=True)

    logger.info("meetings.rsvp.deleted", requested=len(uids), marked=deleted)
    return deleted
