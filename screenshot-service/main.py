from __future__ import annotations

import ipaddress
import json
import logging
import os
import time
from urllib.parse import urlparse

from aiohttp import web
from playwright.async_api import Browser, Playwright, Route, async_playwright

from cookie_utils import normalize_session_cookie_for_probe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("screenshot-service")

_start_time = time.time()

MAX_WIDTH = int(os.environ.get("MAX_WIDTH", "1920"))
MAX_HEIGHT = int(os.environ.get("MAX_HEIGHT", "1080"))
MIN_WIDTH = max(1, int(os.environ.get("MIN_WIDTH", "100")))
MIN_HEIGHT = max(1, int(os.environ.get("MIN_HEIGHT", "100")))
DEFAULT_WIDTH = int(os.environ.get("DEFAULT_WIDTH", "1280"))
DEFAULT_HEIGHT = int(os.environ.get("DEFAULT_HEIGHT", "720"))
PAGE_TIMEOUT_MS = int(os.environ.get("PAGE_TIMEOUT_MS", "30000"))

_SERVICE_SECRET: str = os.environ.get("SCREENSHOT_SERVICE_SECRET", "")

_ALLOWED_ORIGINS_RAW: str = os.environ.get("SCREENSHOT_ALLOWED_ORIGINS", "")
_ALLOWED_ORIGINS: list[str] = [
    o.rstrip("/").lower() for o in _ALLOWED_ORIGINS_RAW.split(",") if o.strip()
]

_INTERNAL_NETS = [
    ipaddress.ip_network(n)
    for n in [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "::1/128",
        "fc00::/7",
        "169.254.0.0/16",
    ]
]

_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]


def _check_secret(request: web.Request) -> web.Response | None:
    """Return 401 if the shared-secret header is absent or wrong."""
    if not _SERVICE_SECRET:
        return _error(
            503, "service not configured: SCREENSHOT_SERVICE_SECRET is not set"
        )
    provided = request.headers.get("X-Screenshot-Secret", "")
    if not provided or provided != _SERVICE_SECRET:
        logger.warning("screenshot.unauthorized remote=%s", request.remote)
        return _error(401, "unauthorized")
    return None


def _is_internal_host(hostname: str) -> bool:
    """Return True if hostname is a literal internal IP."""
    try:
        addr = ipaddress.ip_address(hostname)
        return any(addr in net for net in _INTERNAL_NETS)
    except ValueError:
        return False


def _validate_screenshot_url(url: str) -> str | None:
    """Return an error string or None when the URL is safe to screenshot."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "invalid url"

    if parsed.scheme not in ("http", "https"):
        return "url scheme must be http or https"

    hostname = parsed.hostname or ""
    if not hostname:
        return "url must have a host"

    if _is_internal_host(hostname):
        return "url resolves to an internal address"

    if not _ALLOWED_ORIGINS:
        return "SCREENSHOT_ALLOWED_ORIGINS is not configured — screenshot endpoint is disabled"

    origin = f"{parsed.scheme}://{parsed.netloc}".lower()
    if not any(
        origin == allowed or origin.startswith(allowed + "/")
        for allowed in _ALLOWED_ORIGINS
    ):
        logger.warning(
            "screenshot.blocked_url url=%s allowed=%s", url, _ALLOWED_ORIGINS
        )
        return "url origin is not in the allowed list"

    return None


async def _block_all_network(route: Route) -> None:
    """Intercept handler that allows only data: / blob: URIs and blocks everything else.

    Used in the PDF render context to prevent SSRF via HTML content.
    """
    try:
        scheme = urlparse(route.request.url).scheme
    except Exception:
        await route.abort()
        return
    if scheme in ("data", "blob"):
        await route.continue_()
    else:
        logger.debug("pdf.blocked_resource url=%.120s", route.request.url)
        await route.abort()


async def _startup(app: web.Application) -> None:
    pw: Playwright = await async_playwright().start()
    browser: Browser = await pw.chromium.launch(args=_LAUNCH_ARGS)
    app["pw"] = pw
    app["browser"] = browser
    if not _SERVICE_SECRET:
        logger.error(
            "SCREENSHOT_SERVICE_SECRET is not set — "
            "all requests will be rejected with 503"
        )
    if not _ALLOWED_ORIGINS:
        logger.error(
            "SCREENSHOT_ALLOWED_ORIGINS is not set — "
            "screenshot endpoint will reject all URLs"
        )
    if "--no-sandbox" in _LAUNCH_ARGS:
        logger.warning(
            "browser.no_sandbox: Chromium is running without sandbox "
            "(--no-sandbox). This is a security degradation; only acceptable "
            "inside an isolated container. Do NOT expose this service publicly."
        )
    logger.info(
        "browser.started allowed_origins=%s",
        _ALLOWED_ORIGINS if _ALLOWED_ORIGINS else "NONE",
    )


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
    configured = bool(_SERVICE_SECRET) and bool(_ALLOWED_ORIGINS)
    sandbox_disabled = "--no-sandbox" in _LAUNCH_ARGS
    return web.Response(
        text=json.dumps(
            {
                "status": "ok",
                "uptime": uptime,
                "configured": configured,
                "sandbox_disabled": sandbox_disabled,
            }
        ),
        content_type="application/json",
    )


async def take_screenshot(request: web.Request) -> web.Response:
    auth_err = _check_secret(request)
    if auth_err:
        return auth_err

    url = request.rel_url.query.get("url", "").strip()
    if not url:
        return _error(400, "url parameter is required")

    url_err = _validate_screenshot_url(url)
    if url_err:
        return _error(400, url_err)

    try:
        raw_w = request.rel_url.query.get("width")
        raw_h = request.rel_url.query.get("height")
        width = int(raw_w) if raw_w is not None else DEFAULT_WIDTH
        height = int(raw_h) if raw_h is not None else DEFAULT_HEIGHT
    except ValueError:
        return _error(400, "width and height must be integers")
    if not (MIN_WIDTH <= width <= MAX_WIDTH):
        return _error(400, f"width must be between {MIN_WIDTH} and {MAX_WIDTH}")
    if not (MIN_HEIGHT <= height <= MAX_HEIGHT):
        return _error(400, f"height must be between {MIN_HEIGHT} and {MAX_HEIGHT}")

    full_page = request.rel_url.query.get("full_page", "false").lower() == "true"
    browser: Browser = request.app["browser"]

    logger.info(
        "screenshot.start url=%s %dx%d full_page=%s", url, width, height, full_page
    )
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
        logger.info(
            "screenshot.done url=%s elapsed_ms=%d size=%d",
            url,
            elapsed,
            len(image_bytes),
        )
        return web.Response(
            body=image_bytes,
            content_type="image/png",
            headers={"X-Elapsed-Ms": str(elapsed)},
        )
    except Exception:
        logger.exception("screenshot.error url=%s", url)
        return _error(500, "screenshot failed")


async def render_pdf(request: web.Request) -> web.Response:
    auth_err = _check_secret(request)
    if auth_err:
        return auth_err

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
            await page.route("**/*", _block_all_network)
            await page.set_content(html, wait_until="domcontentloaded")
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={
                    "top": "20mm",
                    "bottom": "20mm",
                    "left": "15mm",
                    "right": "15mm",
                },
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
    except Exception:
        logger.exception("pdf.error")
        return _error(500, "pdf render failed")


def _error(status: int, message: str) -> web.Response:
    return web.Response(
        status=status,
        text=json.dumps({"error": message}),
        content_type="application/json",
    )


async def run_probe(request: web.Request) -> web.Response:
    """Synthetic user-flow probe — drives a browser through a named flow.

    Returns JSON ``{ok, elapsed_ms, flow, step_failed?}``. Unlike
    ``/screenshot`` (which renders arbitrary URLs), this endpoint runs only
    predefined named flows — it targets the portal's own internal services,
    so the SSRF allowlist does not apply (service-to-service call).

    Flow ``login_and_load``: navigate to the frontend login page, authenticate
    via local-auth (POST /api/v1/auth/local/login), assert the SPA shell
    (``#app``) renders and URL is no longer ``/login``. Credentials come from
    the ``PROBE_ADMIN_EMAIL`` / ``PROBE_ADMIN_PASSWORD`` env vars (set by the
    backend worker, defaults empty → probe returns ``configured: false``).

    The payload may carry ``portal_base_url`` (the external portal URL from
    runtime SystemSettings). When present, it is sent as the ``Origin`` header
    on the login POST so the request clears the backend's CSRF Origin-check:
    the probe otherwise authenticates from an internal DNS name (``frontend``)
    that does not match ``portal_base_url`` → ``403 CSRF: Origin mismatch``.
    """
    auth_err = _check_secret(request)
    if auth_err:
        return auth_err

    try:
        body = await request.json()
        flow = body.get("flow", "")
    except Exception:
        return _error(400, "invalid JSON body")

    if flow != "login_and_load":
        return _error(400, f"unknown flow: {flow!r} (supported: login_and_load)")

    # External portal URL — used to spoof Origin on the login POST (CSRF bypass
    # for the service-to-service probe). Absent when the worker couldn't read
    # SystemSettings; login will then fail with 403 on CSRF Origin mismatch.
    portal_base_url = (body.get("portal_base_url") or "").strip()

    admin_email = os.environ.get("PROBE_ADMIN_EMAIL", "")
    admin_password = os.environ.get("PROBE_ADMIN_PASSWORD", "")
    frontend_url = os.environ.get("PROBE_FRONTEND_URL", "http://frontend:80")

    if not admin_email or not admin_password:
        return web.Response(
            text=json.dumps(
                {
                    "ok": False,
                    "configured": False,
                    "flow": flow,
                    "error": "PROBE_ADMIN_EMAIL/PASSWORD not set",
                }
            ),
            content_type="application/json",
        )

    if not portal_base_url:
        logger.warning(
            "probe.no_portal_base_url flow=%s — login will fail CSRF Origin-check",
            flow,
        )

    browser: Browser = request.app["browser"]
    logger.info("probe.start flow=%s", flow)
    t0 = time.time()
    step_failed = None
    try:
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        try:
            page = await context.new_page()
            # 1. Navigate to login page.
            try:
                await page.goto(
                    f"{frontend_url}/login",
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT_MS,
                )
            except Exception:
                step_failed = "navigate_login"
                raise
            # 2. Local-auth login via API (avoid brittle OIDC redirect dance).
            # Origin is spoofed to portal_base_url so the request passes the
            # backend CSRF Origin-check (probe reaches backend via the internal
            # `frontend` DNS name, which differs from the external portal URL).
            try:
                login_headers: dict[str, str] = {}
                if portal_base_url:
                    login_headers["Origin"] = portal_base_url
                resp = await page.request.post(
                    f"{frontend_url}/api/v1/auth/local/login",
                    data={"email": admin_email, "password": admin_password},
                    headers=login_headers,
                    timeout=PAGE_TIMEOUT_MS,
                )
                if resp.status >= 400:
                    step_failed = f"login_status_{resp.status}"
                    raise RuntimeError(f"login returned {resp.status}")
            except Exception:
                if step_failed is None:
                    step_failed = "login_request"
                raise
            # 2b. On production the backend stamps portal_session with
            # ``Secure`` (is_production → True). Chromium does not send
            # Secure cookies over the internal HTTP frontend URL, so the
            # SPA's bootstrap request would arrive without a session → 401
            # → redirect to SSO → assert_app_shell timeout. Re-stamp the
            # session as non-secure for the internal HTTP navigation. This
            # is the same trust-boundary relaxation as the Origin-spoof
            # above (service-to-service in a trusted network). No-op on dev
            # where the cookie is already non-secure. See cookie_utils.py.
            override = normalize_session_cookie_for_probe(
                await context.cookies(), frontend_url
            )
            if override is not None:
                await context.add_cookies([override])
            # 3. Reload + assert SPA shell rendered (session cookie now set).
            try:
                await page.goto(
                    frontend_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS
                )
                await page.wait_for_selector("#app", timeout=PAGE_TIMEOUT_MS)
            except Exception:
                step_failed = step_failed or "assert_app_shell"
                raise
            # 4. Assert we're not still on /login (login succeeded).
            if "/login" in page.url:
                step_failed = "still_on_login"
                raise RuntimeError("URL still /login after login")
        finally:
            await context.close()
        elapsed = round((time.time() - t0) * 1000)
        logger.info("probe.done flow=%s ok=true elapsed_ms=%d", flow, elapsed)
        return web.Response(
            text=json.dumps(
                {"ok": True, "configured": True, "flow": flow, "elapsed_ms": elapsed}
            ),
            content_type="application/json",
            headers={"X-Elapsed-Ms": str(elapsed)},
        )
    except Exception:
        elapsed = round((time.time() - t0) * 1000)
        logger.exception("probe.error flow=%s step=%s", flow, step_failed)
        return web.Response(
            text=json.dumps(
                {
                    "ok": False,
                    "configured": True,
                    "flow": flow,
                    "elapsed_ms": elapsed,
                    "step_failed": step_failed,
                }
            ),
            content_type="application/json",
            status=200,  # 200 with ok=false — the probe ran, the flow failed
        )


def build_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(_startup)
    app.on_cleanup.append(_shutdown)
    app.router.add_get("/health", health)
    app.router.add_get("/screenshot", take_screenshot)
    app.router.add_post("/screenshot", take_screenshot)
    app.router.add_post("/pdf", render_pdf)
    app.router.add_post("/probe", run_probe)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9000"))
    logger.info("screenshot-service starting on port %d", port)
    web.run_app(build_app(), host="0.0.0.0", port=port, access_log=logger)
