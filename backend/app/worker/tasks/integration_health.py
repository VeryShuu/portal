"""Periodic health probes for external integrations.

Runs every 60 s via ARQ cron. Each integration (Keycloak, Nextcloud, SMTP,
Collabora) is probed with a short timeout; results (1 = up, 0 = down) are
written to the Redis hash ``INTEGRATION_HEALTH_KEY``. ``refresh_custom_metrics``
then includes them in ``metrics:snapshot`` so the API process can hydrate the
``portal_integration_up`` gauge.

Design constraints:
- A probe must **never** raise — wrap everything in try/except. A slow/hung
  integration should not stall the worker.
- Probes are **gated**: an integration is only checked when it is configured
  (settings present / module enabled). An unconfigured integration simply
  produces no data point.
- Timeouts are aggressive (3-5 s) — this is a liveness probe, not a full
  transaction. We want fast feedback when something is down.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import cast

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

INTEGRATION_HEALTH_KEY = "integration:health"
INTEGRATION_HEALTH_TTL = 300  # seconds — stale if not refreshed in 5 min

_PROBE_TIMEOUT = 5.0


async def _probe_keycloak() -> bool | None:
    """Check Keycloak reachability via the public OIDC discovery endpoint.

    Returns ``None`` when Keycloak is not configured (no settings file) —
    in that case the probe is skipped (no data point emitted).
    """
    from app.services.keycloak.settings import _get_kc_settings

    kc = _get_kc_settings()
    if not kc.keycloak_url or not kc.keycloak_realm:
        return None  # not configured
    base = kc.keycloak_url.rstrip("/")
    url = f"{base}/realms/{kc.keycloak_realm}/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            resp = await client.get(url)
        return cast(bool, resp.status_code == 200)
    except Exception as exc:
        logger.warning("integration.keycloak_probe_failed", error=str(exc))
        return False


async def _probe_nextcloud() -> bool | None:
    """Check Nextcloud reachability via ``status.php``.

    Returns ``None`` when the Nextcloud module is disabled.
    """
    from app.core.modules_config import load_modules
    from app.services.nextcloud import get_nextcloud_service

    modules = load_modules()
    if not modules.nextcloud.enabled:
        return None  # module disabled
    # Reuse the existing health_check (GET status.php), but guard against
    # misconfiguration: if service account isn't set, health_check still
    # works (it only hits the public status.php endpoint).
    try:
        nc = await get_nextcloud_service()
        return await nc.health_check()
    except Exception as exc:
        logger.warning("integration.nextcloud_probe_failed", error=str(exc))
        return False


async def _probe_smtp() -> bool | None:
    """Check SMTP reachability via a raw TCP connect (no SMTP handshake).

    Returns ``None`` when SMTP is not configured (empty host).
    """
    from app.services.email_settings import read_email_settings

    cfg = read_email_settings()
    if not cfg or not cfg.host:
        return None  # not configured
    try:
        _, _writer = await asyncio.wait_for(
            asyncio.open_connection(cfg.host, cfg.port), timeout=_PROBE_TIMEOUT
        )
        _writer.close()
        with contextlib.suppress(Exception):
            await _writer.wait_closed()
        return True
    except Exception as exc:
        logger.warning("integration.smtp_probe_failed", error=str(exc))
        return False


async def _probe_collabora() -> bool | None:
    """Check Collabora (via Nextcloud richdocuments app) reachability.

    Returns ``None`` when Nextcloud module is disabled (Collabora is only
    available through NC). The probe checks the richdocuments app endpoint.
    """
    from app.core.modules_config import load_modules
    from app.core.system_config import load_system_settings

    modules = load_modules()
    if not modules.nextcloud.enabled:
        return None  # NC disabled → Collabora N/A
    sys_cfg = load_system_settings()
    nc_url = (sys_cfg.nextcloud_url or "").rstrip("/")
    if not nc_url:
        return None
    url = f"{nc_url}/index.php/apps/richdocuments/"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            # 200 = app installed; 404 = not installed; any response = NC reachable.
            # We consider 200/302/404 as "Collabora endpoint reachable".
            resp = await client.get(url)
        return resp.status_code in (200, 302, 404)
    except Exception as exc:
        logger.warning("integration.collabora_probe_failed", error=str(exc))
        return False


async def _probe_erp_sync() -> bool | None:
    """Свежесть ERP-синхронизации.

    Делегирует в :func:`erp_sync.probe_erp_sync` (читает ``erp_sync_runs`` для
    последнего успешного импорта). ``None`` — модуль/poll выключены;
    ``True`` — свежий импорт; ``False`` — протух/ошибок/не было.
    """
    from app.worker.tasks.erp_sync import probe_erp_sync

    return await probe_erp_sync()


async def probe_integrations(ctx: dict) -> dict[str, int]:
    """Run all integration probes and persist results to Redis.

    Called every 60 s by ARQ cron. Writes ``{integration: "1"|"0"}`` to the
    Redis hash ``INTEGRATION_HEALTH_KEY`` (TTL 5 min). ``refresh_custom_metrics``
    picks it up into the metrics snapshot on its own 30 s cadence.
    """
    from typing import Any

    probes: dict[str, Any] = {
        "keycloak": _probe_keycloak,
        "nextcloud": _probe_nextcloud,
        "smtp": _probe_smtp,
        "collabora": _probe_collabora,
        "erp_sync": _probe_erp_sync,
    }

    results: dict[str, int] = {}
    for name, probe in probes.items():
        try:
            outcome = await probe()
        except Exception as exc:  # pragma: no cover - belt and suspenders
            logger.warning("integration.probe_unexpected_error", integration=name, error=str(exc))
            outcome = False
        # None = not configured → skip (no data point). 1/0 = up/down.
        if outcome is not None:
            results[name] = 1 if outcome else 0

    redis = ctx.get("redis")
    if redis is not None and results:
        try:
            mapping = {k: str(v) for k, v in results.items()}
            await redis.hset(INTEGRATION_HEALTH_KEY, mapping=mapping)
            await redis.expire(INTEGRATION_HEALTH_KEY, INTEGRATION_HEALTH_TTL)
        except Exception as exc:  # pragma: no cover - never break the cron
            logger.warning("integration.probe_publish_failed", error=str(exc))

    logger.info("integration.probed", results=results)
    return results
