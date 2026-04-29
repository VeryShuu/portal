"""Singleton Playwright Chromium for PDF export (P1-18).

Launching ``chromium.launch()`` per request adds ~1-2 s latency and risks OOM
under concurrent load. We launch one browser at app startup and reuse it for
every export, opening a short-lived ``BrowserContext`` per render so pages
remain isolated.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_pw: Any = None
_browser: Any = None
_lock = asyncio.Lock()


async def startup_browser() -> None:
    global _pw, _browser
    if _browser is not None:
        return
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # pragma: no cover
        logger.warning("pdf.playwright_unavailable", error=str(exc))
        return
    async with _lock:
        if _browser is not None:
            return
        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(args=["--no-sandbox"])
        logger.info("pdf.browser_started")


async def shutdown_browser() -> None:
    global _pw, _browser
    async with _lock:
        if _browser is not None:
            with contextlib.suppress(Exception):  # pragma: no cover
                await _browser.close()
            _browser = None
        if _pw is not None:
            with contextlib.suppress(Exception):  # pragma: no cover
                await _pw.stop()
            _pw = None
    logger.info("pdf.browser_stopped")


async def render_pdf(html: str) -> bytes:
    """Render an HTML string to A4 PDF bytes using the singleton browser."""
    global _browser
    if _browser is None:
        await startup_browser()
    if _browser is None:  # pragma: no cover
        raise RuntimeError("Playwright browser is unavailable")

    context = await _browser.new_context()
    try:
        page = await context.new_page()
        await page.set_content(html, wait_until="networkidle")
        return await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"},
        )
    finally:
        await context.close()
