from __future__ import annotations

from fastapi import Depends, HTTPException

from app.api.deps import RedisDep
from app.core.modules_config import load_modules_shared

__all__ = ["MeetingsGuard", "meetings_enabled_guard"]


async def meetings_enabled_guard(redis: RedisDep) -> None:
    settings = await load_modules_shared(redis)
    if not settings.meetings.enabled:
        raise HTTPException(status_code=404, detail="Meetings module disabled")


MeetingsGuard = Depends(meetings_enabled_guard)
