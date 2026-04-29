"""Open-redirect guard for ?redirect=... query params."""

from __future__ import annotations

import re

# matches paths like "/foo", "/foo/bar?x=1#h" but NOT "//evil", "/\\evil",
# "javascript:..." etc. (browsers normalise back-slash to slash, so we treat
# them equivalently when validating).
_SAFE_PATH = re.compile(r"^/(?![/\\])[A-Za-z0-9_\-./?#&=%@:+,~!]*$")

_BLOCKED_PREFIXES = ("/api/", "/realms/", "/auth/")


def safe_redirect(value: str | None, default: str = "/") -> str:
    """Return ``value`` if it is a safe relative URL, else ``default``.

    Rules:
        * must start with a single ``/``
        * must not start with ``//`` or ``/\`` (protocol-relative bypass)
        * must not target backend or IdP prefixes that would loop the user
          back through the auth flow
        * only printable URL-safe ASCII allowed
    """
    if not value:
        return default
    candidate = value.replace("\\", "/")
    if not _SAFE_PATH.match(candidate):
        return default
    if any(candidate.startswith(p) for p in _BLOCKED_PREFIXES):
        return default
    return candidate
