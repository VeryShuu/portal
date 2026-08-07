from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.meetings import MeetingBooking, MeetingBookingRoom, MeetingRoom
from app.schemas.meetings import InvitedUser

from ._types import BookingDiff, ConflictInfo

logger = get_logger(__name__)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _date_range(d: date, tz_name: str = "UTC") -> tuple[datetime, datetime]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz).astimezone(UTC)
    end = datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=tz).astimezone(UTC)
    return start, end


async def _load_booking(db: AsyncSession, booking_id: uuid.UUID) -> MeetingBooking | None:
    result = await db.execute(
        select(MeetingBooking)
        .where(MeetingBooking.id == booking_id)
        .options(selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room))
    )
    return result.scalar_one_or_none()


async def _get_conflict_details(
    db: AsyncSession,
    room_ids: list[uuid.UUID],
    start_time: datetime,
    end_time: datetime,
    exclude_booking_id: uuid.UUID | None = None,
) -> list[ConflictInfo]:
    stmt = (
        select(MeetingBookingRoom, MeetingBooking, MeetingRoom)
        .join(MeetingBooking, MeetingBookingRoom.booking_id == MeetingBooking.id)
        .join(MeetingRoom, MeetingBookingRoom.room_id == MeetingRoom.id)
        .where(
            MeetingBookingRoom.room_id.in_(room_ids),
            MeetingBookingRoom.start_time < end_time,
            MeetingBookingRoom.end_time > start_time,
        )
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(MeetingBookingRoom.booking_id != exclude_booking_id)

    result = await db.execute(stmt)
    rows = result.all()

    conflicts: list[ConflictInfo] = []
    for br, booking, room in rows:
        conflicts.append(
            ConflictInfo(
                room_name=room.name,
                booking_title=booking.title,
                start=br.start_time,
                end=br.end_time,
            )
        )
    return conflicts


async def _verify_rooms_active(db: AsyncSession, room_ids: list[uuid.UUID]) -> list[MeetingRoom]:
    result = await db.execute(
        select(MeetingRoom).where(
            MeetingRoom.id.in_(room_ids),
            MeetingRoom.is_active.is_(True),
        )
    )
    rooms = list(result.scalars().all())
    found_ids = {r.id for r in rooms}
    missing = [rid for rid in room_ids if rid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rooms not found or inactive: {[str(m) for m in missing]}",
        )
    return rooms


def invited_users_to_jsonb(invited: list[InvitedUser]) -> list[dict]:
    """Дамп списка приглашённых в dict для записи в JSONB ``invited_users``.

    Поле ``absence`` намеренно **выбрасывается**: статус отсутствия
    (отпуск/болезнь/командировка) не персистится в JSONB-слепок, т.к.
    пересчитывается cron'ом из ERP и устарел бы за сутки. Он обогащается «на
    лету» в выдаче (``booking_to_out`` / live-поиск) и в письме-приглашении
    (см. :mod:`app.services.meetings.absence_enrichment`).

    Без этого.strip'а `model_dump()` оставил бы в dict ``AbsenceInfo`` с
    ``datetime.date``-полями, а SQLAlchemy при JSONB-сериализации падает с
    ``TypeError: Object of type date is not JSON serializable`` — ровно это и
    происходило в проде при отправке фронтендом участника с заполненным
    ``absence`` (только у отсутствующих сотрудников).

    Args:
        invited: список приглашённых (входные данные из Pydantic-схемы).

    Returns:
        Список plain-dict'ов без ``absence``, готовых к записи в JSONB.
    """
    return [u.model_dump(exclude={"absence"}) for u in invited]


def _compute_diff(
    old_users: list[dict],
    new_users: list[InvitedUser],
    non_participant_changed: bool,
) -> BookingDiff:
    valid_old: list[dict] = []
    for u in old_users:
        if not u.get("user_id") or not u.get("email"):
            logger.warning("meetings.diff.malformed_user", entry=u)
            continue
        valid_old.append(u)

    old_ids = {u["user_id"] for u in valid_old}
    new_ids = {u.user_id for u in new_users}

    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids
    unchanged_ids = old_ids & new_ids

    old_by_id = {u["user_id"]: u for u in valid_old}
    new_by_id = {u.user_id: u for u in new_users}

    return BookingDiff(
        added_users=[new_by_id[uid] for uid in added_ids if uid in new_by_id],
        removed_users=[
            InvitedUser(
                user_id=old_by_id[uid]["user_id"],
                full_name=old_by_id[uid].get("full_name", ""),
                email=old_by_id[uid]["email"],
            )
            for uid in removed_ids
            if uid in old_by_id
        ],
        unchanged_users=[new_by_id[uid] for uid in unchanged_ids if uid in new_by_id],
        non_participant_changed=non_participant_changed,
    )
