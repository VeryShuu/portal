"""Characterization-тесты политики cookie-флага Secure (ADR-021, audit PA-004).

Контракт: ``Secure`` определяется фактическим протоколом запроса
(``X-Forwarded-Proto``, fallback — схема запроса), а не ``ENVIRONMENT``.
Раньше точки выдачи читали ``get_settings().is_production``: HTTP-bootstrap
в production получал Secure-куку, которую браузер молча отбрасывал
(логин 200 → следующий запрос 401), а staging-HTTPS — куку без Secure.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.cookies import request_is_secure


def _request(xfp: str | None = None, scheme: str = "http") -> Request:
    headers = []
    if xfp is not None:
        headers.append((b"x-forwarded-proto", xfp.encode()))
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "query_string": b"",
        "scheme": scheme,
        # Реальный ASGI-scope всегда содержит server — без него starlette
        # URL не восстанавливает scheme (см. starlette.datastructures.URL).
        "server": ("testserver", 80),
    }
    return Request(scope)


class TestRequestIsSecure:
    @pytest.mark.parametrize("xfp", ["https", "HTTPS"])
    def test_forwarded_proto_https_is_secure(self, xfp):
        assert request_is_secure(_request(xfp=xfp)) is True

    def test_forwarded_proto_http_is_not_secure(self):
        assert request_is_secure(_request(xfp="http")) is False

    def test_fallback_to_request_scheme(self):
        assert request_is_secure(_request()) is False  # scheme=http, заголовка нет
        assert request_is_secure(_request(scheme="https")) is True


class TestCookieIssuanceSitesFollowPolicy:
    """Каждая точка выдачи: HTTP → без Secure, HTTPS → c Secure."""

    def _assert_flag(self, set_cookie_headers: list[str], prefix: str, *, secure: bool) -> None:
        cookie = next(h for h in set_cookie_headers if h.startswith(prefix))
        has_secure = "secure" in cookie.lower()
        assert has_secure is secure, f"{prefix}: expected secure={secure}, got {cookie!r}"

    def test_oidc_session_cookies(self):
        from app.api.auth import _build_session_cookie_response

        for xfp, expected in (("http", False), ("https", True)):
            resp = _build_session_cookie_response(_request(xfp=xfp), "/", "sid")
            cookies = resp.headers.getlist("set-cookie")
            self._assert_flag(cookies, "portal_session=", secure=expected)
            self._assert_flag(cookies, "portal_auth_method=", secure=expected)

    def test_sso_attempts_cookie(self):
        from fastapi.responses import RedirectResponse

        from app.api.auth._helpers import _set_sso_attempts_cookie

        for xfp, expected in (("http", False), ("https", True)):
            redirect = RedirectResponse(url="/x")
            _set_sso_attempts_cookie(_request(xfp=xfp), redirect, [123.0])
            cookies = redirect.headers.getlist("set-cookie")
            self._assert_flag(cookies, "sso_attempts=", secure=expected)

    def test_refresh_session_cookie(self):
        from app.api.auth.me import _set_session_cookie

        for xfp, expected in (("http", False), ("https", True)):
            resp = JSONResponse({})
            _set_session_cookie(_request(xfp=xfp), resp, "sid")
            cookies = resp.headers.getlist("set-cookie")
            self._assert_flag(cookies, "portal_session=", secure=expected)

    def test_learning_session_cookie(self):
        from app.services.learning.accounts_service import set_session_cookie

        for secure, expected in ((False, False), (True, True)):
            resp = JSONResponse({})
            set_session_cookie(resp, "sid", secure=secure)
            cookies = resp.headers.getlist("set-cookie")
            self._assert_flag(cookies, "learning_session=", secure=expected)


class TestCsrfMiddlewareCookie:
    """CSRF-пара XSRF-TOKEN: Secure по протоколу запроса, не по окружению."""

    def _client(self) -> TestClient:
        async def index(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        from app.middleware.csrf import csrf_protection

        app = Starlette(
            routes=[Route("/", index, methods=["GET"])],
            middleware=[Middleware(BaseHTTPMiddleware, dispatch=csrf_protection)],
        )
        return TestClient(app)

    def test_xsrf_cookie_secure_follows_forwarded_proto(self):
        client = self._client()
        r_http = client.get("/", headers={"X-Forwarded-Proto": "http"})
        cookie = next(
            h for h in r_http.headers.get_list("set-cookie") if h.startswith("XSRF-TOKEN=")
        )
        assert "secure" not in cookie.lower()

        client = self._client()
        r_https = client.get("/", headers={"X-Forwarded-Proto": "https"})
        cookie = next(
            h for h in r_https.headers.get_list("set-cookie") if h.startswith("XSRF-TOKEN=")
        )
        assert "secure" in cookie.lower()
