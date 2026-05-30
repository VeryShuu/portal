from __future__ import annotations

from app.core.logging import get_logger

from ._crud import create_booking, delete_booking, update_booking
from ._helpers import (
    _compute_diff,
    _date_range,
    _get_conflict_details,
    _load_booking,
    _to_utc,
    _verify_rooms_active,
)
from ._queries import get_booking, list_bookings, list_my_bookings
from ._types import (
    MY_BOOKINGS_LIMIT_MAX,
    BookingConflict,
    BookingDiff,
    ConflictInfo,
)

logger = get_logger(__name__)

__all__ = [
    "MY_BOOKINGS_LIMIT_MAX",
    "BookingConflict",
    "BookingDiff",
    "ConflictInfo",
    "_compute_diff",
    "_date_range",
    "_get_conflict_details",
    "_load_booking",
    "_to_utc",
    "_verify_rooms_active",
    "create_booking",
    "delete_booking",
    "get_booking",
    "list_bookings",
    "list_my_bookings",
    "logger",
    "update_booking",
]
