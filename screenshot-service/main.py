from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from aiohttp import web
from playwright.async_api import Browser, Playwright, async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("screenshot-service")

_start_time = time.time()

MAX_WIDTH = int(os.environ.get("MAX_WIDTH", "1920"))
MAX_HEIGHT = int(os.environ.get("MAX_HEIGHT", "1080"))
DEFAULT_WIDTH = int(os.environ.get("DEFAULT_WIDTH", "1280"))
DEFAULT_HEIGHT = int(os.environ.get("DEFAULT_HEIGHT", "720"))
PAGE_TIMEOUT_MS = int(os.environ.get("PAGE_TIMEOUT_MS", "30000"))

_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]


async def _startup(app: web.Application) -> None:
    pw: Playwright = await async_playwright().start()
    browser: Browser = await pw.chromium.launch(args=_LAUNCH_ARGS)
    app["pw"] = pw
    app["browser"] = browser
    logger.info("browser.started")


async def _shutdown(app: web.Application) -> None:
    try:
        await app["browser"].close()
    except Exception:
        pass
    try:
        await app["pw"].stop()
    except Exception:
        pass
    logger.info("browser.stopped")


async def health(request: web.Request) -> web.Response:
    uptime = int(time.time() - _start_time)
    return web.Response(
        text=json.dumps({"status": "ok", "uptime": uptime}),
        content_type="application/json",
    )


async def take_screenshot(request: web.Request) -> web.Response:
    url = request.rel_url.query.get("url", "").strip()
    if not url:
        return _error(400, "url parameter is required")
    if not url.startswith(("http://", "https://")):
        return _error(400, "url must start with http:// or https://")

    try:
        width = min(int(request.rel_url.query.get("width", DEFAULT_WIDTH)), MAX_WIDTH)
        height = min(int(request.rel_url.query.get("height", DEFAULT_HEIGHT)), MAX_HEIGHT)
    except ValueError:
        return _error(400, "width and height must be integers")

    full_page = request.rel_url.query.get("full_page", "false").lower() == "true"
    browser: Browser = request.app["browser"]

    logger.info("screenshot.start url=%s %dx%d full_page=%s", url, width, height, full_page)
    t0 = time.time()
    try:
        context = await browser.new_context(viewport={"width": width, "height": height})
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
            image_bytes = await page.screenshot(type="png", full_page=full_page)
        finally:
            await context.close()
        elapsed = round((time.time() - t0) * 1000)
        logger.info("screenshot.done url=%s elapsed_ms=%d size=%d", url, elapsed, len(image_bytes))
        return web.Response(
            body=image_bytes,
            content_type="image/png",
            headers={"X-Elapsed-Ms": str(elapsed)},
        )
    except Exception as exc:
        logger.exception("screenshot.error url=%s", url)
        return _error(500, str(exc))


async def render_pdf(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        html: str = body.get("html", "")
    except Exception:
        html = await request.text()

    if not html:
        return _error(400, "html is required")

    browser: Browser = request.app["browser"]

    logger.info("pdf.start html_len=%d", len(html))
    t0 = time.time()
    try:
        context = await browser.new_context()
        try:
            page = await context.new_page()
            await page.set_content(html, wait_until="networkidle")
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"},
            )
        finally:
            await context.close()
        elapsed = round((time.time() - t0) * 1000)
        logger.info("pdf.done elapsed_ms=%d size=%d", elapsed, len(pdf_bytes))
        return web.Response(
            body=pdf_bytes,
            content_type="application/pdf",
            headers={"X-Elapsed-Ms": str(elapsed)},
        )
    except Exception as exc:
        logger.exception("pdf.error")
        return _error(500, str(exc))


def _error(status: int, message: str) -> web.Response:
    return web.Response(
        status=status,
        text=json.dumps({"error": message}),
        content_type="application/json",
    )


def build_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(_startup)
    app.on_cleanup.append(_shutdown)
    app.router.add_get("/health", health)
    app.router.add_get("/screenshot", take_screenshot)
    app.router.add_post("/screenshot", take_screenshot)
    app.router.add_post("/pdf", render_pdf)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9000"))
    logger.info("screenshot-service starting on port %d", port)
    web.run_app(build_app(), host="0.0.0.0", port=port, access_log=logger)
