from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.schemas.meetings import InvitedUser

MY_BOOKINGS_LIMIT_MAX = 50

# Hard cap for the GET /meetings/bookings calendar endpoint. Mirrors the
# `le` on the Query param in app/api/meetings/bookings.py — keep in lockstep.
BOOKINGS_LIMIT_MAX = 200


@dataclass
class ConflictInfo:
    room_name: str
    booking_title: str
    start: datetime
    end: datetime


class BookingConflict(Exception):  # noqa: N818
    def __init__(self, conflicts: list[ConflictInfo]) -> None:
        super().__init__("Booking conflict")
        self.conflicts = conflicts


@dataclass
class BookingDiff:
    added_users: list[InvitedUser] = field(default_factory=list)
    removed_users: list[InvitedUser] = field(default_factory=list)
    unchanged_users: list[InvitedUser] = field(default_factory=list)
    non_participant_changed: bool = False
    old_series_uid: str | None = None
