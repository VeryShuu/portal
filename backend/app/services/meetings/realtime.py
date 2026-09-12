from __future__ import annotations

import json
import uuid

from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)

MEETINGS_STREAM_KEY = "notifications:meetings"


async def publish_meeting_event(
    redis: Redis,
    *,
    action: str,
    booking_id: uuid.UUID,
    room_ids: list[uuid.UUID],
    date_str: str,
) -> None:
    try:
        await redis.xadd(
            MEETINGS_STREAM_KEY,
            {
                "type": "meeting_changed",
                "action": action,
                "booking_id": str(booking_id),
                "room_ids": json.dumps([str(r) for r in room_ids]),
                "date": date_str,
            },
            maxlen=10000,
            approximate=True,
        )
    except Exception as exc:
        logger.warning(
            "meetings.realtime.publish_failed",
            error=str(exc),
            action=action,
            booking_id=str(booking_id),
        )
