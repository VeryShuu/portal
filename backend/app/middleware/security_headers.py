from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import Response


async def security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Apply baseline security headers.

    Note: Content-Security-Policy is intentionally NOT set here. Nginx is the
    single source of truth for CSP (with dynamic frame-src derived from system
    settings) and uses ``proxy_hide_header Content-Security-Policy`` to drop
    any upstream copy. Setting CSP both here and in nginx caused duplicate
    headers and inconsistent policies for proxied vs. non-proxied responses.
    """
    from app.core.config import get_settings

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # X-XSS-Protection: 0 — отключаем устаревший фильтр XSS в IE/legacy-Chrome,
    # т.к. современные браузеры опираются на CSP, а сам фильтр исторически
    # создавал XS-Leak уязвимости (см. https://blog.sheddow.xyz/css-timing-attack/).
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if get_settings().is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
