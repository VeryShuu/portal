"""Server-side SSO redirect URL builder for service links.

The ``id_token_hint`` is appended to the target URL from the user's session so
it never reaches the client in a response body — only via the ``Location``
header of the server-issued redirect.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Request
from redis.asyncio import Redis

from app.core.security import SESSION_COOKIE_NAME
from app.services.session import get_session


async def build_sso_url(link_url: str, request: Request, redis: Redis) -> str:
    """Append ``id_token_hint`` from the session to ``link_url`` when available."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    id_token_hint = ""
    if session_id:
        session_data = await get_session(redis, session_id)
        id_token_hint = (session_data or {}).get("id_token", "")

    if id_token_hint:
        separator = "&" if "?" in link_url else "?"
        return f"{link_url}{separator}{urlencode({'id_token_hint': id_token_hint})}"
    return link_url
