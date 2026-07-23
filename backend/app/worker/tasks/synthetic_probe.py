"""Synthetic user-flow probe — calls screenshot-service /probe endpoint.

Runs every 5 minutes via ARQ cron. Drives a headless browser through the
``login_and_load`` flow (local-auth login + SPA shell assertion) via the
screenshot-service's Playwright instance. Results go to a Redis hash consumed
by ``refresh_custom_metrics`` → ``portal_synthetic_probe_ok`` /
``portal_synthetic_probe_duration_seconds`` gauges.

Gating: if ``PROBE_ADMIN_EMAIL`` / ``PROBE_ADMIN_PASSWORD`` are not set in the
worker environment, the probe is skipped (the screenshot-service returns
``configured: false`` and we record nothing).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

SYNTHETIC_PROBE_KEY = "synthetic:probe"
SYNTHETIC_PROBE_TTL = 900  # 15 min — stale if not refreshed (3 missed cycles)
_PROBE_FLOW_TIMEOUT = 45.0  # seconds — Playwright flow can take 10-30s


async def run_synthetic_probe(ctx: dict) -> dict | None:
    """Run the synthetic login flow and persist the result to Redis.

    Returns the probe result dict (``{ok, flow, elapsed_ms, ...}``) or ``None``
    when credentials are not configured (probe skipped).
    """
    base = settings.screenshot_service_url.rstrip("/")
    url = f"{base}/probe"
    secret = settings.screenshot_service_secret

    try:
        async with httpx.AsyncClient(timeout=_PROBE_FLOW_TIMEOUT) as client:
            resp = await client.post(
                url,
                json={"flow": "login_and_load"},
                headers={"X-Screenshot-Secret": secret},
            )
        data: dict[str, Any] = resp.json()
    except Exception as exc:
        logger.warning("synthetic.probe_call_failed", error=str(exc))
        data = {"ok": False, "configured": True, "flow": "login_and_load",
                "step_failed": "service_unreachable"}

    flow = data.get("flow", "login_and_load")
    # configured=False (no creds in screenshot-service) → skip, record nothing.
    if not data.get("configured", True):
        logger.info("synthetic.probe_skipped", reason="not_configured")
        return None

    ok = 1 if data.get("ok") else 0
    elapsed_ms = data.get("elapsed_ms", 0)

    redis = ctx.get("redis")
    if redis is not None:
        try:
            mapping = {f"{flow}:ok": str(ok), f"{flow}:ms": str(elapsed_ms)}
            await redis.hset(SYNTHETIC_PROBE_KEY, mapping=mapping)
            await redis.expire(SYNTHETIC_PROBE_KEY, SYNTHETIC_PROBE_TTL)
        except Exception as exc:  # pragma: no cover - never break the cron
            logger.warning("synthetic.probe_publish_failed", error=str(exc))

    logger.info(
        "synthetic.probed",
        flow=flow,
        ok=bool(ok),
        elapsed_ms=elapsed_ms,
        step_failed=data.get("step_failed"),
    )
    return data
