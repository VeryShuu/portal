from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import BackgroundTasks, Request

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.services.meetings.bookings_service import BookingDiff

logger = get_logger(__name__)


def schedule_email_dispatch(
    background: BackgroundTasks,
    request: Request,
    booking,
    action: str,
    diff: BookingDiff | None = None,
) -> None:
    async def _run() -> None:
        try:
            from app.services.meetings.notifications import dispatch_meeting_emails

            await dispatch_meeting_emails(booking=booking, action=action, diff=diff)
        except Exception as exc:
            logger.exception(
                "meetings.emails.dispatch_failed",
                error=str(exc),
                booking_id=str(booking.id),
                action=action,
            )

    background.add_task(_run)
    _ = request  # request kept for signature compatibility (background task uses own session)
