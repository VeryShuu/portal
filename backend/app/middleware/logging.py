import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import Response

from app.core.logging import (
    bind_request_context,
    clear_request_context,
    get_logger,
)

logger = get_logger(__name__)


async def request_logging(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Логирование HTTP-запросов с correlation.

    - Генерирует request_id (или принимает из заголовка X-Request-Id от балансера).
    - Биндит request_id/method/path/client_ip в contextvars для всех логов запроса.
    - Уровень лога выбирается по status_code: 5xx → error, 4xx → warning, остальное → info.
    - Slow request (elapsed_ms > LOG_SLOW_REQUEST_MS) логируется как warning.
    - Необработанное исключение логируется через exception(), ContextVars очищаются в finally.
    """
    incoming_rid = request.headers.get("X-Request-Id")
    request_id = incoming_rid if incoming_rid and len(incoming_rid) <= 128 else str(uuid.uuid4())
    start = time.perf_counter()

    client_ip = (
        request.headers.get("X-Real-IP")
        or (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )

    clear_request_context()
    bind_request_context(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=client_ip,
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "http.request_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            elapsed_ms=elapsed_ms,
        )
        raise
    finally:
        clear_request_context()

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    sc = response.status_code

    if sc >= 500:
        log_method = logger.error
    elif sc >= 400:
        log_method = logger.warning
    else:
        from app.core.system_config import load_system_settings

        _slow_ms = load_system_settings().log_slow_request_ms
        log_method = (
            logger.warning if _slow_ms > 0 and elapsed_ms >= _slow_ms else logger.info
        )

    log_method(
        "http.request",
        status_code=sc,
        elapsed_ms=elapsed_ms,
    )
    response.headers["X-Request-Id"] = request_id
    return response
