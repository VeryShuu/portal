import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import Response

from app.core.logging import get_logger
from app.core.security import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS
from app.services.session import _session_key

_SESSION_EXTEND_PATHS_SKIP = frozenset({"/health", "/ready", "/metrics"})

logger = get_logger(__name__)
_SESSION_EXTEND_MIN_INTERVAL = 300  # extend TTL no more than once per 5 minutes per session


async def session_sliding_window(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Extend session TTL on each authenticated request (sliding window).

    Prevents active users from being logged out mid-work after 8 hours.
    Throttled to one Redis call per session per 5 minutes.
    """
    response = await call_next(request)

    if request.url.path in _SESSION_EXTEND_PATHS_SKIP:
        return response

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return response

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return response

    try:
        throttle_key = f"sess_ext_ts:{session_id}"
        last_str = await redis.get(throttle_key)
        now = time.time()
        if last_str is None or now - float(last_str) >= _SESSION_EXTEND_MIN_INTERVAL:
            await redis.expire(_session_key(session_id), SESSION_TTL_SECONDS)
            await redis.setex(throttle_key, _SESSION_EXTEND_MIN_INTERVAL, str(now))
    except Exception as exc:
        logger.debug("session.sliding_window_extend_failed", error=str(exc))

    return response
