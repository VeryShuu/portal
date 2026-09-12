"""IMAP transport helpers for Helpdesk ingress.

This module deliberately knows nothing about ticket persistence: it owns only
the IMAP protocol boundary, while ``ingress.py`` keeps poll orchestration and
its transaction/rollback guarantees.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskMailboxSettings

logger = get_logger(__name__)

_LITERAL_RE = re.compile(rb"\{\d+\}")


def _make_imap_client_raw(*, host: str, port: int, use_ssl: bool) -> Any:
    """Create an aioimaplib client without connecting to the server."""
    import aioimaplib

    if use_ssl:
        return aioimaplib.IMAP4_SSL(host=host, port=port)
    return aioimaplib.IMAP4(host=host, port=port)


def _make_imap_client(settings_row: HelpdeskMailboxSettings) -> Any:
    return _make_imap_client_raw(
        host=settings_row.imap_host,
        port=settings_row.imap_port,
        use_ssl=settings_row.imap_use_ssl,
    )


async def probe_imap_connection(
    *, host: str, port: int, username: str, password: str, use_ssl: bool, folder: str
) -> tuple[bool, str]:
    """Connect, authenticate and select a folder for mailbox settings probe."""
    try:
        client = _make_imap_client_raw(host=host, port=port, use_ssl=use_ssl)
        await asyncio.wait_for(client.wait_hello_from_server(), timeout=10)
        await asyncio.wait_for(client.login(username, password), timeout=10)
        response = await client.select(folder)
        ok = "OK" in response[0] if response else False
        await client.logout()
        return (
            (True, f"Connected, selected '{folder}'")
            if ok
            else (False, f"select failed: {response}")
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def _search_all(client: Any) -> list[str]:
    """Return every UID in the currently selected folder."""
    typ, data = await client.search("ALL")
    if typ != "OK" or not data or not data[0]:
        return []
    raw = data[0]
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="ignore")
    return [uid for uid in raw.split() if uid]


def _extract_rfc822(data: Any) -> bytes | None:
    """Extract RFC822 bytes from aioimaplib's flat or legacy tuple response."""
    items = list(data)
    for index, item in enumerate(items):
        if (
            isinstance(item, (bytes, bytearray))
            and _LITERAL_RE.search(bytes(item))
            and index + 1 < len(items)
            and isinstance(items[index + 1], (bytes, bytearray))
        ):
            return bytes(items[index + 1])
    for item in items:
        if isinstance(item, tuple):
            for part in item:
                if isinstance(part, (bytes, bytearray)) and not _LITERAL_RE.search(bytes(part)):
                    return bytes(part)
    return None


async def _safe_seen(client: Any, uid: str) -> None:
    """Mark a message seen without making the poll fail on IMAP errors."""
    try:
        await client.store(uid, "+FLAGS", "\\Seen")
    except Exception:
        logger.warning("helpdesk.ingress.mark_seen_failed", uid=uid, exc_info=True)


async def _safe_delete(client: Any, uid: str) -> None:
    """Mark a message deleted; poll orchestration performs EXPUNGE later."""
    try:
        await client.store(uid, "+FLAGS", "\\Deleted")
    except Exception:
        logger.warning("helpdesk.ingress.mark_deleted_failed", uid=uid, exc_info=True)
