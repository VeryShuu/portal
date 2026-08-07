from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.meetings import AbsenceInfo, BookingOut, InvitedUser, RoomOut
from app.services.meetings.absence_enrichment import enrich_absences_for_invited


async def booking_to_out(db: AsyncSession, booking: Any) -> BookingOut:
    """Конвертация ORM-бронирования в ``BookingOut`` с enrich отсутствий.

    Статус отсутствия участников (отпуск/отгул/болезнь/командировка) считается
    «на лету» на дату встречи (``booking.start_time.date()``), а не хранится в
    JSONB-слепке ``invited_users`` (он пересчитывается cron'ом из ERP и устарел
    бы за сутки). См. :mod:`app.services.meetings.absence_enrichment`.
    """
    rooms = [RoomOut.model_validate(br.room) for br in booking.rooms]
    invited = [InvitedUser(**u) for u in (booking.invited_users or [])]
    await _apply_absences(db, booking, invited)
    return _build_out(booking, rooms, invited)


async def bookings_to_out(db: AsyncSession, bookings: list[Any]) -> list[BookingOut]:
    """Batch-конвертация списка бронирований (защита от N+1 в list-endpoint'ах).

    Группирует бронирования по дате встречи и для каждой даты делает один
    bulk-запрос отсутствий для всех приглашённых этой даты. Для типичных
    list-view (день/неделя/месяц) это 1–31 запрос вместо N×M.
    """
    if not bookings:
        return []

    prepared: list[tuple[Any, list[InvitedUser]]] = [
        (b, [InvitedUser(**u) for u in (b.invited_users or [])]) for b in bookings
    ]

    # Один bulk-запрос на каждую уникальную дату встречи.
    grouped: dict[date, list[InvitedUser]] = defaultdict(list)
    for booking, invited in prepared:
        grouped[booking.start_time.date()].extend(invited)

    absences_by_date: dict[date, dict[str, AbsenceInfo]] = {}
    for on_date, date_invited in grouped.items():
        absences_by_date[on_date] = await enrich_absences_for_invited(
            db, date_invited, on_date=on_date
        )

    out: list[BookingOut] = []
    for booking, invited in prepared:
        absences = absences_by_date[booking.start_time.date()]
        for u in invited:
            u.absence = absences.get(u.email.lower())
        rooms = [RoomOut.model_validate(br.room) for br in booking.rooms]
        out.append(_build_out(booking, rooms, invited))
    return out


async def _apply_absences(db: AsyncSession, booking: Any, invited: list[InvitedUser]) -> None:
    """Заполнить ``InvitedUser.absence`` для одного бронирования (in-place)."""
    if not invited:
        return
    absences = await enrich_absences_for_invited(
        db, booking.invited_users or [], on_date=booking.start_time.date()
    )
    for u in invited:
        u.absence = absences.get(u.email.lower())


def _build_out(booking: Any, rooms: list[RoomOut], invited: list[InvitedUser]) -> BookingOut:
    return BookingOut(
        id=booking.id,
        title=booking.title,
        organizer_name=booking.organizer_name,
        creator_id=booking.creator_id,
        description=booking.description,
        start_time=booking.start_time,
        end_time=booking.end_time,
        rooms=rooms,
        invited_users=invited,
        series_id=booking.series_id,
        recurrence_rule=booking.recurrence_rule,
        update_count=booking.update_count,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )
