"""Schedule the screenshot-service synthetic user-flow probe.

The screenshot-service owns probe credentials and exports probe metrics directly.
The worker only triggers ``login_and_load`` every five minutes and records the
structured outcome in logs. Keeping the metrics at the executor makes disabled,
stale, failed, and successful states observable without copying credentials into
the worker or routing state through Redis and the backend metrics snapshot.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

SYNTHETIC_PROBE_FLOW = "login_and_load"
_PROBE_FLOW_TIMEOUT = 45.0


async def run_synthetic_probe(_ctx: dict) -> dict | None:
    """Trigger the synthetic login flow and return its reported outcome.

    ``None`` means that screenshot-service reported the probe disabled. Transport
    and invalid-response failures are returned as an explicit unavailable result;
    screenshot-service keeps ``last_completed`` unchanged in those cases.
    """
    base = settings.screenshot_service_url.rstrip("/")
    url = f"{base}/probe"
    secret = settings.screenshot_service_secret

    portal_base_url = ""
    try:
        from app.core.system_config import load_system_settings

        portal_base_url = load_system_settings().portal_base_url or ""
    except Exception as exc:  # pragma: no cover - never break the cron
        logger.warning("synthetic.portal_base_url_failed", error=str(exc))

    try:
        async with httpx.AsyncClient(timeout=_PROBE_FLOW_TIMEOUT) as client:
            resp = await client.post(
                url,
                json={"flow": SYNTHETIC_PROBE_FLOW, "portal_base_url": portal_base_url},
                headers={"X-Screenshot-Secret": secret},
            )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if not isinstance(data.get("configured"), bool):
            raise ValueError("probe response has no boolean configured field")
        if data.get("flow") != SYNTHETIC_PROBE_FLOW:
            raise ValueError("probe response has an unexpected flow")
    except Exception as exc:
        logger.warning("synthetic.probe_call_failed", error=str(exc))
        return {
            "ok": False,
            "configured": None,
            "flow": SYNTHETIC_PROBE_FLOW,
            "step_failed": "service_unavailable",
        }

    if not data["configured"]:
        logger.info("synthetic.probe_skipped", reason="not_configured")
        return None

    logger.info(
        "synthetic.probed",
        flow=SYNTHETIC_PROBE_FLOW,
        ok=bool(data.get("ok")),
        elapsed_ms=data.get("elapsed_ms"),
        step_failed=data.get("step_failed"),
    )
    return data
