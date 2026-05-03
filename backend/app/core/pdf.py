"""PDF export via screenshot-service (P1-18).

Delegates rendering to the dedicated screenshot-service container so that
the backend process does not need to manage a Chromium instance itself.
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def render_pdf(html: str) -> bytes:
    """Send HTML to screenshot-service and return A4 PDF bytes."""
    url = f"{get_settings().screenshot_service_url.rstrip('/')}/pdf"
    logger.info("pdf.request url=%s html_len=%d", url, len(html))

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json={"html": html})
        resp.raise_for_status()

    logger.info("pdf.done size=%d", len(resp.content))
    return resp.content
