from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Request, status

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.meetings import MeetingsGuard
from app.api.meetings._mappers import booking_to_out as _booking_to_out
from app.core.logging import get_logger
from app.schemas.meetings import (
    BookingConflictOut,
    BookingCreate,
    BookingDelete,
    BookingOut,
    BookingUpdate,
    ConflictDetail,
    SeriesUpdate,
)
from app.services.meetings.audit import (
    MEETING_CREATED,
    MEETING_DELETED,
    MEETING_SERIES_CREATED,
    MEETING_UPDATED,
    SERIES_DELETED,
    SERIES_UPDATED,
    push_meetings_audit,
)
from app.services.meetings.bookings_service import (
    MY_BOOKINGS_LIMIT_MAX,
    BookingConflict,
    delete_booking,
    get_booking,
    list_bookings,
    list_my_bookings,
    update_booking,
)
from app.services.meetings.bookings_service import (
    create_booking as svc_create_booking,
)
from app.services.meetings.dispatch import schedule_email_dispatch
from app.services.meetings.realtime import publish_meeting_event
from app.services.meetings.series_service import delete_series, update_series

router = APIRouter(
    prefix="/meetings/bookings",
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


@router.get("/my", response_model=list[BookingOut])
async def list_my(
    user: CurrentUser,
    db: DbDep,
    start_date: date | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=MY_BOOKINGS_LIMIT_MAX),
) -> list[BookingOut]:
    bookings = await list_my_bookings(db, user_id=user.id, start_date=start_date, limit=limit)
    return [_booking_to_out(b) for b in bookings]


@router.get("", response_model=list[BookingOut])
async def list_bookings_endpoint(
    user: CurrentUser,
    db: DbDep,
    date: date | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    room_id: uuid.UUID | None = Query(default=None),
    creator_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[BookingOut]:
    if start_date is not None and end_date is not None:
        if (end_date - start_date).days > 90:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Date range must not exceed 90 days",
            )
    bookings = await list_bookings(
        db,
        date=date,
        start_date=start_date,
        end_date=end_date,
        room_id=room_id,
        creator_id=creator_id,
        limit=limit,
        offset=offset,
    )
    return [_booking_to_out(b) for b in bookings]


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def create_booking_endpoint(
    payload: BookingCreate,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    background: BackgroundTasks,
) -> BookingOut:
    if payload.recurrence is not None:
        from app.services.meetings.series_service import create_booking_series

        try:
            bookings = await create_booking_series(db, payload=payload, user=user)
        except BookingConflict as exc:
            _raise_conflict(exc)

        first = bookings[0]
        await db.commit()
        await push_meetings_audit(
            action=MEETING_SERIES_CREATED,
            user=user,
            request=request,
            resource_type="series",
            resource_id=first.series_id,
            resource_title=first.title,
            details={
                "count": len(bookings),
                "first_id": str(first.id),
                "until": bookings[-1].start_time.date().isoformat(),
            },
        )

        for b in bookings:
            room_ids = [br.room_id for br in b.rooms]
            await publish_meeting_event(
                redis,
                action="created",
                booking_id=b.id,
                room_ids=room_ids,
                date_str=b.start_time.date().isoformat(),
            )

        # Strategy A: send one iCal-with-RRULE to each invitee (uses the
        # canonical first instance whose UID == series-...@domain and
        # which carries the RRULE).
        schedule_email_dispatch(background, request, first, "created", None)

        logger.info(
            "meetings.series.created",
            series_id=str(first.series_id),
            count=len(bookings),
            user=str(user.id),
        )
        return _booking_to_out(first)

    try:
        booking = await svc_create_booking(db, payload=payload, user=user)
    except BookingConflict as exc:
        _raise_conflict(exc)

    room_ids = [br.room_id for br in booking.rooms]
    await db.commit()
    await push_meetings_audit(
        action=MEETING_CREATED,
        user=user,
        request=request,
        resource_type="booking",
        resource_id=booking.id,
        resource_title=booking.title,
    )

    await publish_meeting_event(
        redis,
        action="created",
        booking_id=booking.id,
        room_ids=room_ids,
        date_str=booking.start_time.date().isoformat(),
    )

    schedule_email_dispatch(background, request, booking, "created", None)

    logger.info("meetings.booking.created", booking_id=str(booking.id), user=str(user.id))
    return _booking_to_out(booking)


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking_endpoint(
    booking_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> BookingOut:
    booking = await get_booking(db, booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return _booking_to_out(booking)


@router.put("/{booking_id}", response_model=BookingOut)
async def update_booking_endpoint(
    booking_id: uuid.UUID,
    payload: BookingUpdate,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    background: BackgroundTasks,
) -> BookingOut:
    # If the user opted to apply the change to the entire series, route the
    # request to the series-update service so every instance is updated atomically.
    existing = await get_booking(db, booking_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if payload.apply_to == "series" and existing.series_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking is not part of a series",
        )

    if payload.apply_to == "series" and existing.series_id is not None:
        series_payload = SeriesUpdate(
            title=payload.title,
            description=payload.description,
            invited_users=payload.invited_users,
            start_time=payload.start_time,
            end_time=payload.end_time,
            room_ids=payload.room_ids,
        )
        try:
            bookings, diff = await update_series(
                db, series_id=existing.series_id, payload=series_payload, user=user
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
            resource_id=existing.series_id,
            resource_title=first.title,
            details={"count": len(bookings)},
        )

        for b in bookings:
            room_ids = [br.room_id for br in b.rooms]
            await publish_meeting_event(
                redis,
                action="updated",
                booking_id=b.id,
                room_ids=room_ids,
                date_str=b.start_time.date().isoformat(),
            )

        schedule_email_dispatch(background, request, first, "updated", diff)

        # Return the originally addressed booking, refreshed.
        target = next((b for b in bookings if b.id == booking_id), first)
        return _booking_to_out(target)

    try:
        booking, diff = await update_booking(db, booking_id=booking_id, payload=payload, user=user)
    except BookingConflict as exc:
        _raise_conflict(exc)

    room_ids = [br.room_id for br in booking.rooms]
    await db.commit()
    await push_meetings_audit(
        action=MEETING_UPDATED,
        user=user,
        request=request,
        resource_type="booking",
        resource_id=booking.id,
        resource_title=booking.title,
    )

    await publish_meeting_event(
        redis,
        action="updated",
        booking_id=booking.id,
        room_ids=room_ids,
        date_str=booking.start_time.date().isoformat(),
    )

    schedule_email_dispatch(background, request, booking, "updated", diff)

    logger.info("meetings.booking.updated", booking_id=str(booking.id), user=str(user.id))
    return _booking_to_out(booking)


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking_endpoint(
    booking_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    background: BackgroundTasks,
    payload: BookingDelete | None = Body(default=None),
) -> None:
    existing = await get_booking(db, booking_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    apply_to = (payload.apply_to if payload is not None else "this")

    if apply_to == "series" and existing.series_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking is not part of a series",
        )

    if apply_to == "series" and existing.series_id is not None:
        series_id = existing.series_id
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

        for b in bookings:
            room_ids = [br.room_id for br in b.rooms]
            await publish_meeting_event(
                redis,
                action="deleted",
                booking_id=b.id,
                room_ids=room_ids,
                date_str=b.start_time.date().isoformat(),
            )

        if bookings:
            schedule_email_dispatch(background, request, bookings[0], "cancelled", None)

        logger.info(
            "meetings.series.deleted",
            series_id=str(series_id),
            count=len(bookings),
            user=str(user.id),
        )
        return

    booking = await delete_booking(db, booking_id=booking_id, user=user)

    room_ids = [br.room_id for br in booking.rooms]
    await db.commit()
    await push_meetings_audit(
        action=MEETING_DELETED,
        user=user,
        request=request,
        resource_type="booking",
        resource_id=booking_id,
        resource_title=booking.title,
    )

    await publish_meeting_event(
        redis,
        action="deleted",
        booking_id=booking_id,
        room_ids=room_ids,
        date_str=booking.start_time.date().isoformat(),
    )

    schedule_email_dispatch(background, request, booking, "cancelled", None)

    logger.info("meetings.booking.deleted", booking_id=str(booking_id), user=str(user.id))
