"""Helpers for cookie handling in the synthetic probe flow.

Pure functions (no I/O) so they can be unit-tested without a browser.

Why this module exists — see ``docs/monitoring.md`` § "Synthetic probes":
the probe logs in via the API (POST /api/v1/auth/local/login) and then
navigates the SPA over the **internal HTTP** docker URL
(``PROBE_FRONTEND_URL``, default ``http://nginx:80``). On a production
deployment ``ENVIRONMENT=production`` makes the backend stamp the session
cookie with ``Secure`` (``is_production`` in
``app/api/auth/local.py``). Chromium does not send ``Secure`` cookies over
plain HTTP, so the session never reaches the SPA's bootstrap request →
``GET /bootstrap`` returns 401 → SPA redirects to SSO → probe times out at
``assert_app_shell``. This is invisible on dev (``Secure`` is off there),
hence the regression slipped through.

The fix mirrors the existing ``Origin``-spoof on the login POST: the probe
already runs service-to-service in a trusted network, so re-stamping the
session cookie as non-secure for the internal HTTP navigation is the same
kind of trust-boundary relaxation. It is a no-op when the cookie is already
non-secure (dev) — only the production case is patched.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

SESSION_COOKIE_NAME = "portal_session"


def normalize_session_cookie_for_probe(
    cookies: list[dict[str, Any]],
    frontend_url: str,
) -> dict[str, Any] | None:
    """Return a non-``Secure`` re-stamp of the session cookie, or ``None``.

    Given the BrowserContext cookie store (``context.cookies()`` output)
    and the internal ``frontend_url`` the probe navigates over, returns a
    cookie dict suitable for ``context.add_cookies([...])`` that re-issues
    the session cookie **without** ``Secure`` so the browser sends it on the
    subsequent plain-HTTP SPA navigation.

    Returns ``None`` when:

    - there is no ``portal_session`` cookie (login didn't issue one), or
    - the cookie is already non-secure (dev) — no override needed.

    The returned dict keeps the original ``httpOnly`` / ``sameSite`` / value
    and infers ``domain``/``path`` from ``frontend_url`` (which is how the
    login response set it — host-scoped, no explicit ``domain=``).
    """
    session = next(
        (c for c in cookies if c.get("name") == SESSION_COOKIE_NAME),
        None,
    )
    if session is None:
        return None
    if not session.get("secure", False):
        # Dev (ENVIRONMENT != production): cookie is already HTTP-eligible,
        # nothing to fix. Returning None makes the caller skip add_cookies.
        return None

    parsed = urlparse(frontend_url)
    domain = parsed.hostname or ""
    # SameSite=Lax matches the backend's set_cookie() for portal_session.
    return {
        "name": SESSION_COOKIE_NAME,
        "value": session.get("value", ""),
        "domain": domain,
        "path": "/",
        "httpOnly": bool(session.get("httpOnly", True)),
        "secure": False,
        "sameSite": session.get("sameSite", "Lax"),
    }
