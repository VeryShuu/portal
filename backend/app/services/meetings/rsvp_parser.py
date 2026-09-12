"""Парсер IMIP-ответов (RFC 6047): Accept/Decline из почтовых клиентов.

Чистые функции без БД/IMAP: на вход сырые RFC822-байты письма, на выход
:dataclass:`ParsedReply` или ``None`` (письмо не является валидным ответом на
приглашение встречи — его поллер обязан не трогать, ящик общий).

Структура письма-ответа (Outlook / Apple Calendar / Thunderbird)::

    From: ivanov@mage.ru
    Message-ID: <...>
    MIME: multipart/mixed
      └─ multipart/alternative
           ├─ text/html  (тело «Иванов принял встречу»)
           └─ text/calendar; method=REPLY
                BEGIN:VCALENDAR
                METHOD:REPLY
                BEGIN:VEVENT
                UID: {booking.id}@{domain}            ← одиночная встреча
                UID: series-{series_id}@{domain}      ← серия
                RECURRENCE-ID;TZID=...:20260901T100000  ← экземпляр серии (опц.)
                ATTENDEE;PARTSTAT=ACCEPTED:mailto:ivanov@mage.ru
                ORGANIZER:mailto:portal@mage.ru
                END:VEVENT
                END:VCALENDAR

Валидация отправителя (From == ATTENDEE, case-insensitive) выполняется здесь:
IMIP-ответ с несвязанным From — подделка/пересылка, его обрабатывать нельзя.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes
from email.utils import parseaddr
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# PARTSTAT (RFC 5545 §3.2.12) → наш статус. NEEDS-ACTION/DELEGATED/COUNTER и
# прочее сознательно не ловим в v1 (COUNTER = «предложить другое время»).
_PARTSTAT_MAP = {
    "ACCEPTED": "accepted",
    "DECLINED": "declined",
    "TENTATIVE": "tentative",
}

# Префикс UID серии из ical_builder.build_ical (_resolve_uid).
_SERIES_UID_PREFIX = "series-"


@dataclass(frozen=True, slots=True)
class ParsedReply:
    """Разобранный IMIP-ответ; всё, что нужно инджесту для записи статуса."""

    message_id: str
    sender_email: str
    attendee_email: str
    status: str  # 'accepted' | 'declined' | 'tentative'
    uid: str
    # RECURRENCE-ID экземпляра серии (aware-datetime); None → одиночная встреча
    # либо ответ «на всю серию» (решение о применении — за инджестом).
    recurrence_id: datetime | None


@dataclass(frozen=True, slots=True)
class ParsedUid:
    """Распознанный UID встречи: либо одиночная, либо серия."""

    booking_id: uuid.UUID | None
    series_id: uuid.UUID | None

    @property
    def is_series(self) -> bool:
        return self.series_id is not None


def parse_uid(uid: str) -> ParsedUid | None:
    """``{booking.id}@domain`` | ``series-{series_id}@domain`` → ParsedUid.

    Домен не сверяем (исторически мог меняться с portal_base_url) —
    достаточно валидного UUID в localpart. Чужие UID → None.
    """
    localpart = uid.split("@", 1)[0].strip()
    if localpart.lower().startswith(_SERIES_UID_PREFIX):
        raw = localpart[len(_SERIES_UID_PREFIX) :]
        try:
            return ParsedUid(booking_id=None, series_id=uuid.UUID(raw))
        except ValueError:
            return None
    try:
        return ParsedUid(booking_id=uuid.UUID(localpart), series_id=None)
    except ValueError:
        return None


def _extract_sender_email(msg: Any) -> str:
    raw = msg.get("From", "") or ""
    return parseaddr(str(raw))[1].strip().lower()


def _extract_message_id(msg: Any) -> str:
    return str(msg.get("Message-ID", "") or "").strip()


def _find_calendar_part(msg: Any) -> bytes | None:
    """Первая ``text/calendar`` MIME-часть (walk по всем уровням вложенности).

    Возвращаем ``None`` для писем без календарного вложения — их поллер
    обязан не трогать (общий ящик: там ERP-отчёты, человеческая переписка,
    отскоки и автоответы).
    """
    for part in msg.walk():
        if part.get_content_type() != "text/calendar":
            continue
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes) and payload:
            return payload
        # compat32: не-MIME часть — текст как str
        raw = part.get_payload()
        if isinstance(raw, str):
            return raw.encode("utf-8", errors="replace")
    return None


def _first_attendee(event: Any) -> tuple[str, str] | None:
    """(email, PARTSTAT) первого ATTENDEE-ответа; None, если нет/не распарсен.

    В REPLY клиент обязан прислать ровно одного ATTENDEE — отвечающего.
    Если несколько (нестандартные клиенты) — берём первого с поддерживаемым
    PARTSTAT.
    """
    attendees = event.get("ATTENDEE")
    if attendees is None:
        return None
    if not isinstance(attendees, list):
        attendees = [attendees]
    for attendee in attendees:
        # vCalAddress — подкласс vText: сам адрес (``mailto:...``), атрибута
        # ``.value`` у него нет (грабля icalendar 5.x, выявлена тестами).
        value = str(attendee).strip()
        if not value.lower().startswith("mailto:"):
            continue
        email = value[len("mailto:") :].strip().lower()
        partstat = str(attendee.params.get("PARTSTAT", "") or "").upper()
        if partstat in _PARTSTAT_MAP:
            return email, _PARTSTAT_MAP[partstat]
    return None


def parse_reply_email(raw: bytes) -> ParsedReply | None:
    """Разобрать письмо; ``None`` = не является валидным ответом на приглашение.

    Причины ``None`` (все — «не трогаем письмо»):
    нет ``text/calendar``-части; METHOD ≠ REPLY (REQUEST/COUNTER/...);
    нет/битый UID; нет ATTENDEE с поддерживаемым PARTSTAT;
    From ≠ ATTENDEE (подделка/пересылка чужого ответа).
    """
    try:
        msg = message_from_bytes(raw)
        cal_bytes = _find_calendar_part(msg)
        if cal_bytes is None:
            return None

        from icalendar import Calendar

        cal = Calendar.from_ical(cal_bytes)
        if str(cal.get("METHOD", "") or "").upper() != "REPLY":
            return None

        events = [c for c in cal.walk("VEVENT")]
        if not events:
            return None
        event = events[0]

        uid = str(event.get("UID", "") or "").strip()
        if not uid or parse_uid(uid) is None:
            return None

        attendee = _first_attendee(event)
        if attendee is None:
            return None
        attendee_email, status = attendee

        sender = _extract_sender_email(msg)
        if not sender or sender != attendee_email:
            logger.warning(
                "meetings.rsvp.sender_mismatch",
                sender=sender,
                attendee=attendee_email,
                uid=uid,
            )
            return None

        recurrence_id = event.get("RECURRENCE-ID")
        recurrence_dt = getattr(recurrence_id, "dt", None)
        if recurrence_dt is not None and not isinstance(recurrence_dt, datetime):
            recurrence_dt = None  # редкий битый RECURRENCE-ID (не-datetime)

        return ParsedReply(
            message_id=_extract_message_id(msg),
            sender_email=sender,
            attendee_email=attendee_email,
            status=status,
            uid=uid,
            recurrence_id=recurrence_dt,
        )
    except Exception as exc:
        # Битое письмо не должно ронять поллер — логируем и пропускаем.
        logger.warning("meetings.rsvp.parse_failed", error=str(exc), error_type=type(exc).__name__)
        return None
