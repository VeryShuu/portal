from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


def get_redis(request: Request) -> Redis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise RuntimeError("Redis is not initialized on app.state")
    return cast(Redis, redis)


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe — checks DB + Redis")
async def ready(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    failed = False

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        logger.exception("readiness_check.postgres_failed", error=str(exc))
        checks["postgres"] = "error"
        failed = True

    try:
        r = get_redis(request)
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.exception("readiness_check.redis_failed", error=str(exc))
        checks["redis"] = "error"
        failed = True

    from app.api.modules import load_modules
    from app.core.system_config import load_system_settings
    from app.services.nextcloud import get_nc_service

    modules = load_modules()
    if modules.nextcloud.enabled:
        sys_settings = load_system_settings()
        if not sys_settings.nextcloud_url:
            checks["nextcloud"] = "unconfigured"
        else:
            try:
                nc = get_nc_service()
                nc_ok = await nc.health_check()
                checks["nextcloud"] = "ok" if nc_ok else "error"
                if not nc_ok:
                    failed = True
            except Exception as exc:
                logger.exception("readiness_check.nextcloud_failed", error=str(exc))
                checks["nextcloud"] = "error"
                failed = True

    audit_ok: bool = getattr(request.app.state, "audit_partitions_ok", True)
    if not audit_ok:
        logger.warning("readiness_check.audit_partitions_missing")
        checks["audit_partitions"] = "error"
        failed = True
    else:
        checks["audit_partitions"] = "ok"

    libmagic_available: bool = getattr(request.app.state, "libmagic_available", True)
    checks["mime_detection"] = "magic" if libmagic_available else "fallback"

    # --- non-fatal integration checks (degraded, not down) ---
    # Keycloak/SMTP/Collabora are probed but never make /ready return 503:
    # the portal stays "ready" if DB+Redis are up, because local-auth fallback
    # and core content features still work. Operators see per-component status
    # in the response body + the PortalIntegrationDown alert (probe_integrations).
    integration_checks = await _probe_optional_integrations()
    checks.update(integration_checks)

    status_code = 503 if failed else 200
    return JSONResponse(
        content={"status": "error" if failed else "ok", "checks": checks},
        status_code=status_code,
    )


async def _probe_optional_integrations() -> dict[str, str]:
    """Probe Keycloak/SMTP/Collabora — non-fatal, status-only.

    Returns a ``{name: "ok"|"error"|"unconfigured"}`` dict. Never raises.
    These do NOT affect the ``/ready`` HTTP status (only DB/Redis/NC do),
    so a degraded integration surfaces as a warning, not a readiness failure.
    """
    result: dict[str, str] = {}
    # Keycloak — reuse the worker probe logic (OIDC discovery endpoint).
    try:
        from app.worker.tasks.integration_health import _probe_keycloak

        kc = await _probe_keycloak()
        result["keycloak"] = "ok" if kc else "unconfigured" if kc is None else "error"
    except Exception as exc:
        # audit [H8]: probe-функция сама упала (не integration-down, а баг в probe).
        # Оператор видит keycloak="error" в /ready, но причина терялась.
        logger.debug("readiness_check.keycloak_probe_crashed", error=str(exc))
        result["keycloak"] = "error"

    # SMTP — TCP connect check.
    try:
        from app.worker.tasks.integration_health import _probe_smtp

        smtp = await _probe_smtp()
        result["smtp"] = "ok" if smtp else "unconfigured" if smtp is None else "error"
    except Exception as exc:
        logger.debug("readiness_check.smtp_probe_crashed", error=str(exc))
        result["smtp"] = "error"

    # Collabora — gated behind Nextcloud module (probed via richdocuments).
    try:
        from app.api.modules import load_modules

        modules = load_modules()
        if modules.nextcloud.enabled:
            from app.worker.tasks.integration_health import _probe_collabora

            coll = await _probe_collabora()
            result["collabora"] = "ok" if coll else "unconfigured" if coll is None else "error"
    except Exception as exc:
        logger.debug("readiness_check.collabora_probe_crashed", error=str(exc))
        result["collabora"] = "error"

    return result
