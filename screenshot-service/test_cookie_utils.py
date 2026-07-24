"""Characterization tests for ``cookie_utils.normalize_session_cookie_for_probe``.

Locks in the regression fix for the synthetic probe failing on production
with ``step_failed=assert_app_shell``. Root cause: on prod the backend
stamps ``portal_session`` with ``Secure`` (``is_production`` → True), and
Chromium does not send Secure cookies over the internal HTTP
``PROBE_FRONTEND_URL`` → ``GET /bootstrap`` returns 401 → SPA redirects to
SSO → ``#app`` never renders → 30s timeout.

These tests run without a browser (the function under test is pure).
"""

from __future__ import annotations

from cookie_utils import normalize_session_cookie_for_probe

_FRONTEND_URL = "http://nginx:80"


def _secure_session_cookie() -> dict:
    """Mimic the production cookie store after a successful local login."""
    return {
        "name": "portal_session",
        "value": "abc123",
        "domain": "nginx",
        "path": "/",
        "httpOnly": True,
        "secure": True,  # ← the production case
        "sameSite": "Lax",
        "expires": 1893456000,
    }


def _plain_session_cookie() -> dict:
    """Mimic the dev cookie store (ENVIRONMENT != production → secure=False)."""
    c = _secure_session_cookie()
    c["secure"] = False
    return c


class TestNormalizeSessionCookieForProbe:
    def test_secure_cookie_overridden_to_non_secure_for_http(self):
        """PROD regression: Secure cookie must be re-stamped without Secure.

        Without this override the browser would silently drop the session on
        the plain-HTTP SPA navigation → /bootstrap 401 → SSO redirect →
        assert_app_shell timeout. This is the exact failure the synthetic
        login panel in Grafana Overview was showing.
        """
        cookies = [_secure_session_cookie()]

        result = normalize_session_cookie_for_probe(cookies, _FRONTEND_URL)

        assert result is not None
        assert result["name"] == "portal_session"
        assert result["value"] == "abc123"
        assert result["secure"] is False  # ← the fix
        assert result["httpOnly"] is True  # preserved
        assert result["sameSite"] == "Lax"  # preserved
        assert result["domain"] == "nginx"  # derived from frontend_url
        assert result["path"] == "/"

    def test_plain_cookie_is_noop(self):
        """Dev case (ENVIRONMENT != production): cookie already HTTP-eligible.

        Returning None signals the caller to skip add_cookies entirely — no
        spurious write, no change in behavior on dev.
        """
        cookies = [_plain_session_cookie()]

        result = normalize_session_cookie_for_probe(cookies, _FRONTEND_URL)

        assert result is None

    def test_missing_session_cookie_returns_none(self):
        """Login did not issue a session (misconfigured creds, etc.).

        Returning None keeps the caller from crashing on the next() default
        and lets the downstream SPA-navigation step fail naturally with its
        own step_failed label.
        """
        cookies = [
            {
                "name": "portal_auth_method",
                "value": "local",
                "domain": "nginx",
                "path": "/",
                "secure": False,
                "httpOnly": False,
                "sameSite": "Lax",
            },
            {
                "name": "XSRF-TOKEN",
                "value": "tok",
                "domain": "nginx",
                "path": "/",
                "secure": False,
                "httpOnly": False,
                "sameSite": "Lax",
            },
        ]

        result = normalize_session_cookie_for_probe(cookies, _FRONTEND_URL)

        assert result is None

    def test_empty_cookie_store_returns_none(self):
        """Defensive: empty store must not raise."""
        result = normalize_session_cookie_for_probe([], _FRONTEND_URL)
        assert result is None

    def test_domain_inferred_from_frontend_url(self):
        """Domain is derived from frontend_url, not from the original cookie.

        Mirrors the backend's host-scoped set_cookie (no explicit domain=).
        The probe reaches backend via ``http://nginx:80`` so the re-stamped
        cookie must be scoped to ``nginx`` to match the navigation origin.
        """
        cookies = [_secure_session_cookie()]

        # Frontend URL with explicit port — domain must still be the bare host.
        result = normalize_session_cookie_for_probe(cookies, "http://nginx:80")

        assert result is not None
        assert result["domain"] == "nginx"

    def test_other_cookies_ignored(self):
        """Only portal_session is touched; XSRF/auth_method stay as-is.

        XSRF-TOKEN is JS-readable (httpOnly=False) and used for double-submit
        CSRF on the frontend. It's also Secure on prod, but the SPA reads it
        via document.cookie which is itself blocked for Secure-over-HTTP —
        that's a separate concern; this probe fix targets the session only.
        """
        cookies = [
            _secure_session_cookie(),
            {"name": "XSRF-TOKEN", "value": "tok", "secure": True},
        ]

        result = normalize_session_cookie_for_probe(cookies, _FRONTEND_URL)

        assert result is not None
        assert result["name"] == "portal_session"
