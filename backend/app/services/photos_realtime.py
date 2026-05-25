"""Realtime SSE publisher for photo lifecycle events."""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)

PHOTOS_STREAM_KEY = "notifications:photos"


async def publish_photo_processed(
    redis: Redis,
    *,
    photo_id: uuid.UUID,
    folder_id: uuid.UUID,
    blurhash: str | None,
) -> None:
    try:
        await redis.xadd(
            PHOTOS_STREAM_KEY,
            {
                "type": "photo_processed",
                "photo_id": str(photo_id),
                "folder_id": str(folder_id),
                "blurhash": blurhash or "",
            },
            maxlen=5000,
            approximate=True,
        )
    except Exception as exc:
        logger.warning(
            "photos.realtime.publish_failed",
            error=str(exc),
            photo_id=str(photo_id),
        )
