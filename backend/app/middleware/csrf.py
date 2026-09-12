import secrets
from collections.abc import Awaitable, Callable
from urllib.parse import ParseResult, urlparse

from fastapi import Request
from fastapi.responses import JSONResponse, Response

_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/auth/callback",
        "/api/v1/auth/logout",
        "/api/v1/auth/learning/logout",
        "/ocs/v2.php/apps/richdocuments/api/v1/federation",
    }
)
_CSRF_ORIGIN_ONLY_PATHS = frozenset(
    {
        "/api/v1/auth/local/login",
        # Публичный контур обучения: cookie/XSRF-пары на вызовах входа ещё нет
        # (шаги 1-2 passwordless: запрос кода + сверка). Остальные API — с токеном.
        "/api/v1/auth/learning/login",
        "/api/v1/auth/learning/verify",
    }
)
CSRF_COOKIE_NAME = "XSRF-TOKEN"
_CSRF_HEADER_NAME = "x-xsrf-token"


def _check_origin(request: Request) -> JSONResponse | None:
    """Origin/Referer должен совпасть с одним из доверенных базовых URL —
    ``portal_base_url`` + ``learning_base_url`` (публичный контур, ADR-051);
    fallback — сам хост запроса (за обратным прокси). None = проверка пройдена."""
    from app.core.system_config import load_system_settings

    settings = load_system_settings()
    allowed = [settings.portal_base_url]
    # Публичный контур обучения: второй доверенный Origin. Пустая настройка
    # (контур не введён) список не расширяет.
    if settings.learning_base_url:
        allowed.append(settings.learning_base_url)
    if not allowed[0]:
        allowed[0] = f"{request.url.scheme}://{request.headers.get('host', '')}"

    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF: Origin header required"},
        )
    actual = urlparse(origin)
    host_fallback = f"{request.url.scheme}://{request.headers.get('host', '')}"
    origin_ok = any(_same_origin(base, actual) for base in (*allowed, host_fallback) if base)
    if not origin_ok:
        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF: Origin mismatch"},
        )
    return None


def _same_origin(base_url: str, actual_parts: ParseResult) -> bool:
    expected = urlparse(base_url)
    return (
        actual_parts.scheme == expected.scheme
        and actual_parts.netloc.lower() == expected.netloc.lower()
    )


def _double_submit_ok(request: Request) -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(_CSRF_HEADER_NAME)
    if not cookie_token or not header_token:
        return False
    return bool(secrets.compare_digest(cookie_token, header_token))


async def csrf_protection(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Defense-in-depth CSRF using two complementary checks:

    1. Origin/Referer must match one of the allowed base URLs —
       ``portal_base_url`` plus ``learning_base_url`` (public learning contour,
       ADR-051), catching simple cross-site form submissions even from browsers
       without modern SameSite support (see :func:`_check_origin`).
    2. Double-submit cookie: the JS-readable ``XSRF-TOKEN`` cookie value must
       match the ``X-XSRF-TOKEN`` header (see :func:`_double_submit_ok`). The
       cookie is auto-issued on the first safe response, the SPA echoes it back
       on every state-changing request via ``api/index.ts`` interceptor.

    Fully exempt paths (no checks): OIDC callback, logout, NC federation.
    Origin-only paths (Origin check but no double-submit): local login,
    learning login/forgot/reset.
    """
    path = request.url.path
    is_safe = request.method in _CSRF_SAFE_METHODS
    is_exempt = path in _CSRF_EXEMPT_PATHS
    is_origin_only = path in _CSRF_ORIGIN_ONLY_PATHS

    if not is_safe and not is_exempt:
        origin_error = _check_origin(request)
        if origin_error is not None:
            return origin_error

        needs_double_submit = not is_origin_only and path.startswith("/api/v1/")
        if needs_double_submit and not _double_submit_ok(request):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF: token mismatch"},
            )

    response = await call_next(request)

    if (
        is_safe
        or path in _CSRF_ORIGIN_ONLY_PATHS  # выдаём пару токенов сразу после логина
        or path == "/api/v1/auth/callback"
    ) and CSRF_COOKIE_NAME not in request.cookies:
        from app.core.cookies import request_is_secure

        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=secrets.token_urlsafe(32),
            httponly=False,
            secure=request_is_secure(request),
            samesite="lax",
            path="/",
        )
    return response
