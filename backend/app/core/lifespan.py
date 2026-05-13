from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

import asyncpg
import sentry_sdk
from arq import create_pool as arq_create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi_limiter import FastAPILimiter
from redis.asyncio import Redis

from app.core.bootstrap import bootstrap_admin
from app.core.config import get_settings
from app.core.limiter import real_ip_identifier
from app.core.logging import get_logger
from app.services.audit_partitions import ensure_partitions as _ensure_partitions
from app.services.keycloak import close_kc_http_client, init_kc_http_client
from app.services.nextcloud import get_nc_service, invalidate_nc_service

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("portal.startup", environment=settings.environment)

    from app.core.system_config import apply_timezone, load_system_settings

    startup_sys = load_system_settings()
    apply_timezone(startup_sys.timezone)
    if not startup_sys.portal_base_url:
        logger.warning(
            "portal.csrf_fallback_mode",
            note=(
                "portal_base_url is empty, CSRF Origin-check uses request Host as fallback"
                " — configure portal_base_url in system settings"
            ),
        )

    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await app.state.redis.ping()
    except Exception as redis_err:
        logger.critical("portal.startup_failed.redis", error=str(redis_err))
        raise RuntimeError(f"Redis unavailable at startup: {redis_err}") from redis_err

    await FastAPILimiter.init(app.state.redis, identifier=real_ip_identifier)
    await init_kc_http_client()
    await bootstrap_admin()

    app.state.arq_pool = await arq_create_pool(RedisSettings.from_dsn(settings.redis_url))

    from app.core.modules_config import load_modules

    try:
        if load_modules().nextcloud.enabled:
            await get_nc_service().ensure_root()
    except Exception as nc_err:
        logger.warning("nc.ensure_root_skipped", error=str(nc_err))
        with suppress(Exception):
            sentry_sdk.capture_exception(nc_err, tags={"startup_degraded": "nextcloud"})

    app.state.audit_partitions_ok = False
    try:
        pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        pg_conn = await asyncpg.connect(pg_url, statement_cache_size=0)
        try:
            created = await _ensure_partitions(pg_conn, months_ahead=3)
            if created:
                logger.info("audit.startup_partitions_created", tables=created)
        finally:
            await pg_conn.close()
        app.state.audit_partitions_ok = True
    except Exception as part_err:
        logger.warning("audit.startup_partitions_failed", error=str(part_err))
        with suppress(Exception):
            sentry_sdk.capture_exception(part_err, tags={"startup_degraded": "audit_partitions"})

    try:
        yield
    finally:
        logger.info("portal.shutdown")
        if hasattr(app.state, "arq_pool") and app.state.arq_pool:
            await app.state.arq_pool.aclose()
        with suppress(Exception):  # pragma: no cover
            await FastAPILimiter.close()
        if hasattr(app.state, "redis") and app.state.redis:
            await app.state.redis.aclose()
        with suppress(Exception):
            await close_kc_http_client()
        with suppress(Exception):
            await invalidate_nc_service()
