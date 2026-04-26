from fastapi import APIRouter
from sqlalchemy import text
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)
settings = get_settings()

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe — checks DB + Redis")
async def ready() -> dict[str, str | dict[str, str]]:
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
        r = get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.exception("readiness_check.redis_failed", error=str(exc))
        checks["redis"] = "error"
        failed = True

    from app.api.modules import load_modules
    from app.api.system_settings import load_system_settings
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

    from fastapi.responses import JSONResponse

    status_code = 503 if failed else 200
    return JSONResponse(
        content={"status": "error" if failed else "ok", "checks": checks},
        status_code=status_code,
    )
