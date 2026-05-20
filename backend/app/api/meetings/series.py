from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.meetings import MeetingsGuard
from app.api.meetings._mappers import booking_to_out as _booking_to_out
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
from app.services.meetings.dispatch import schedule_email_dispatch
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
    background: BackgroundTasks,
) -> list[BookingOut]:
    try:
        bookings, diff = await update_series(
            db, series_id=series_id, payload=payload, user=user
        )
    except BookingConflict as exc:
        _raise_conflict(exc)

    first = bookings[0]
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

    schedule_email_dispatch(background, request, first, "updated", diff)

    logger.info("meetings.series.updated", series_id=str(series_id), user=str(user.id))
    return [_booking_to_out(b) for b in bookings]


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_series_endpoint(
    series_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    background: BackgroundTasks,
) -> None:
    bookings = await delete_series(db, series_id=series_id, user=user)

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

    if bookings:
        schedule_email_dispatch(background, request, bookings[0], "cancelled", None)

    logger.info("meetings.series.deleted", series_id=str(series_id), user=str(user.id))
