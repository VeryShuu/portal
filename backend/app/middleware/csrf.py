import secrets
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse, Response

_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = frozenset({
    "/api/v1/auth/callback",
    "/api/v1/auth/logout",
    "/ocs/v2.php/apps/richdocuments/api/v1/federation",
})
_CSRF_ORIGIN_ONLY_PATHS = frozenset({
    "/api/v1/auth/local/login",
})
CSRF_COOKIE_NAME = "XSRF-TOKEN"
_CSRF_HEADER_NAME = "x-xsrf-token"


async def csrf_protection(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Defense-in-depth CSRF using two complementary checks:

    1. Origin/Referer must match ``portal_base_url`` (catches simple cross-site
       form submissions even from browsers without modern SameSite support).
    2. Double-submit cookie: the JS-readable ``XSRF-TOKEN`` cookie value must
       match the ``X-XSRF-TOKEN`` header. The cookie is auto-issued on the
       first safe response, the SPA echoes it back on every state-changing
       request via ``api/index.ts`` interceptor.

    Fully exempt paths (no checks): OIDC callback, logout, NC federation.
    Origin-only paths (Origin check but no double-submit): local login.
    """
    from app.core.config import get_settings

    path = request.url.path
    is_safe = request.method in _CSRF_SAFE_METHODS
    is_exempt = path in _CSRF_EXEMPT_PATHS
    is_origin_only = path in _CSRF_ORIGIN_ONLY_PATHS

    if not is_safe and not is_exempt:
        from app.core.system_config import load_system_settings

        _base_url = load_system_settings().portal_base_url
        if not _base_url:
            _base_url = f"{request.url.scheme}://{request.headers.get('host', '')}"

        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            expected_parts = urlparse(_base_url)
            actual_parts = urlparse(origin)
            origin_ok = (
                actual_parts.scheme == expected_parts.scheme
                and actual_parts.netloc.lower() == expected_parts.netloc.lower()
            )
            if not origin_ok:
                _fallback = f"{request.url.scheme}://{request.headers.get('host', '')}"
                _fallback_parts = urlparse(_fallback)
                origin_ok = (
                    actual_parts.scheme == _fallback_parts.scheme
                    and actual_parts.netloc.lower() == _fallback_parts.netloc.lower()
                )
            if not origin_ok:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF: Origin mismatch"},
                )
        else:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF: Origin header required"},
            )

        if not is_origin_only and path.startswith("/api/v1/"):
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(_CSRF_HEADER_NAME)
            tokens_match = bool(
                cookie_token
                and header_token
                and secrets.compare_digest(cookie_token, header_token)
            )
            if not tokens_match:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF: token mismatch"},
                )

    response = await call_next(request)

    settings = get_settings()
    if (
        (is_safe or path in {"/api/v1/auth/local/login", "/api/v1/auth/callback"})
        and CSRF_COOKIE_NAME not in request.cookies
    ):
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=secrets.token_urlsafe(32),
            httponly=False,
            secure=settings.is_production,
            samesite="lax",
            path="/",
        )
    return response
