from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.meetings import MeetingsGuard
from app.api.meetings._mappers import bookings_to_out as _bookings_to_out
from app.core.logging import get_logger
from app.schemas.meetings import (
    BookingConflictOut,
    BookingOut,
    ConflictDetail,
    SeriesCountOut,
    SeriesUpdate,
)
from app.services.meetings.audit import SERIES_DELETED, SERIES_UPDATED, push_meetings_audit
from app.services.meetings.bookings_service import BookingConflict
from app.services.meetings.notifications import enqueue_meeting_emails
from app.services.meetings.realtime import publish_meeting_event
from app.services.meetings.series_service import (
    delete_series,
    get_series_count,
    update_series,
)

router = APIRouter(
    prefix="/meetings/series",
    tags=["meetings"],
    dependencies=[MeetingsGuard],
)
logger = get_logger(__name__)


def _raise_conflict(exc: BookingConflict) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=BookingConflictOut(
            conflicts=[
                ConflictDetail(
                    room_name=c.room_name,
                    booking_title=c.booking_title,
                    start=c.start,
                    end=c.end,
                )
                for c in exc.conflicts
            ]
        ).model_dump(),
    )


@router.get("/{series_id}/count", response_model=SeriesCountOut)
async def series_count(
    series_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> SeriesCountOut:
    count = await get_series_count(db, series_id)
    return SeriesCountOut(count=count)


@router.put("/{series_id}", response_model=list[BookingOut])
async def update_series_endpoint(
    series_id: uuid.UUID,
    payload: SeriesUpdate,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> list[BookingOut]:
    try:
        bookings, diff = await update_series(db, series_id=series_id, payload=payload, user=user)
    except BookingConflict as exc:
        _raise_conflict(exc)

    first = bookings[0]
    await enqueue_meeting_emails(db, booking=first, action="updated", diff=diff)
    await db.commit()
    await push_meetings_audit(
        action=SERIES_UPDATED,
        user=user,
        request=request,
        resource_type="series",
        resource_id=series_id,
        resource_title=first.title,
        details={"count": len(bookings)},
    )

    for booking in bookings:
        room_ids = [br.room_id for br in booking.rooms]
        await publish_meeting_event(
            redis,
            action="updated",
            booking_id=booking.id,
            room_ids=room_ids,
            date_str=booking.start_time.date().isoformat(),
        )

    logger.info("meetings.series.updated", series_id=str(series_id), user=str(user.id))
    return await _bookings_to_out(db, bookings)


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_series_endpoint(
    series_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> None:
    bookings = await delete_series(db, series_id=series_id, user=user)

    if bookings:
        await enqueue_meeting_emails(db, booking=bookings[0], action="cancelled", diff=None)
    await db.commit()
    await push_meetings_audit(
        action=SERIES_DELETED,
        user=user,
        request=request,
        resource_type="series",
        resource_id=series_id,
        resource_title=bookings[0].title if bookings else None,
        details={"count": len(bookings)},
    )

    for booking in bookings:
        room_ids = [br.room_id for br in booking.rooms]
        await publish_meeting_event(
            redis,
            action="deleted",
            booking_id=booking.id,
            room_ids=room_ids,
            date_str=booking.start_time.date().isoformat(),
        )

    logger.info("meetings.series.deleted", series_id=str(series_id), user=str(user.id))
