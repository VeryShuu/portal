from __future__ import annotations

from app.schemas.meetings import BookingOut, InvitedUser, RoomOut


def booking_to_out(booking) -> BookingOut:
    rooms = [RoomOut.model_validate(br.room) for br in booking.rooms]
    invited = [InvitedUser(**u) for u in (booking.invited_users or [])]
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
