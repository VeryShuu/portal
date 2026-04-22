import sentry_sdk
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.limiter import real_ip_identifier
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(
    environment=settings.environment,
    log_level=settings.log_level,
    service_name="portal-backend",
    force_json=settings.log_force_json,
)
logger = get_logger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
    )


_BOOTSTRAP_LOCK_KEY = 0x504F5254414C0001  # stable int64 — 'PORTAL\x00\x01'


async def _bootstrap_admin() -> None:
    """При запуске создаёт первого локального admin, если заданы ADMIN_EMAIL + ADMIN_PASSWORD.

    Защищено pg_advisory_xact_lock — только один воркер из всего пула выполнит
    bootstrap, остальные увидят commit первого и выйдут по idempotency-проверке.
    """
    if not settings.admin_email or not settings.admin_password:
        return
    if not settings.local_auth_enabled:
        return

    from datetime import UTC, datetime
    from sqlalchemy import select, text, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.core.database import AsyncSessionLocal
    from app.core.security import hash_password
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _BOOTSTRAP_LOCK_KEY})

        result = await db.execute(select(User).where(User.role == "admin"))
        if result.scalar_one_or_none():
            await db.commit()
            return

        existing_result = await db.execute(select(User).where(User.email == settings.admin_email))
        existing_user = existing_result.scalar_one_or_none()
        if existing_user is not None:
            await db.execute(
                update(User).where(User.email == settings.admin_email).values(role="admin")
            )
            await db.commit()
            logger.warning("bootstrap.admin_upgraded", user_email=settings.admin_email)
            return

        now = datetime.now(UTC)
        stmt = pg_insert(User).values(
            email=settings.admin_email,
            full_name="Administrator",
            auth_source="local",
            password_hash=hash_password(settings.admin_password),
            role="admin",
            updated_at=now,
        ).on_conflict_do_nothing(index_elements=["email"])
        await db.execute(stmt)
        await db.commit()
        logger.info("bootstrap.admin_created", user_email=settings.admin_email)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("portal.startup", environment=settings.environment)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await FastAPILimiter.init(redis, identifier=real_ip_identifier)
    await _bootstrap_admin()
    # P1-18: launch a single Chromium per process and reuse contexts per export.
    from app.core.pdf import startup_browser, shutdown_browser
    await startup_browser()
    try:
        yield
    finally:
        logger.info("portal.shutdown")
        await shutdown_browser()
        try:
            await FastAPILimiter.close()
        except Exception:  # pragma: no cover
            pass
        # P1-21: explicit close to release the limiter's pooled connection.
        await redis.aclose()


app = FastAPI(
    title="Корпоративный портал",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.portal_base_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
)


_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = ("/api/v1/auth/callback",)  # OIDC redirect from Keycloak — no Origin


@app.middleware("http")
async def csrf_origin_check(request: Request, call_next):
    """P1-15: defense-in-depth CSRF check on top of SameSite=Lax cookie.

    Rejects state-changing requests whose Origin/Referer does not match
    ``settings.portal_base_url``. OIDC callback is exempt because Keycloak
    redirects via 302 without an Origin header.
    """
    if request.method not in _CSRF_SAFE_METHODS and not any(
        request.url.path.startswith(p) for p in _CSRF_EXEMPT_PATHS
    ):
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            expected = settings.portal_base_url.rstrip("/")
            if not origin.startswith(expected):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF: Origin mismatch"},
                )
        # No Origin/Referer at all → block (browsers always send one for cross-site).
        else:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF: Origin header required"},
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Логирование HTTP-запросов с correlation.

    - Генерирует request_id (или принимает из заголовка X-Request-Id от балансера).
    - Биндит request_id/method/path/client_ip в contextvars для всех логов запроса.
    - Уровень лога выбирается по status_code: 5xx → error, 4xx → warning, остальное → info.
    - Slow request (elapsed_ms > LOG_SLOW_REQUEST_MS) логируется как warning.
    - Необработанное исключение логируется через exception(), ContextVars очищаются в finally.
    """
    import time
    import uuid
    from app.core.logging import bind_request_context, clear_request_context

    incoming_rid = request.headers.get("X-Request-Id")
    request_id = incoming_rid if incoming_rid and len(incoming_rid) <= 128 else str(uuid.uuid4())
    start = time.perf_counter()

    client_ip = (
        request.headers.get("X-Real-IP")
        or (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )

    clear_request_context()
    bind_request_context(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=client_ip,
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "http.request_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            elapsed_ms=elapsed_ms,
        )
        raise
    finally:
        # contextvars очистятся автоматически при выходе из запроса (async Task),
        # но для безопасности — явно.
        pass

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    sc = response.status_code

    if sc >= 500:
        log_method = logger.error
    elif sc >= 400:
        log_method = logger.warning
    elif elapsed_ms >= settings.log_slow_request_ms:
        log_method = logger.warning
    else:
        log_method = logger.info

    log_method(
        "http.request",
        status_code=sc,
        elapsed_ms=elapsed_ms,
        slow=elapsed_ms >= settings.log_slow_request_ms,
    )
    response.headers["X-Request-Id"] = request_id
    return response


if settings.prometheus_metrics_enabled:
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/ready", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.news import router as news_router
from app.api.links import router as links_router
from app.api.bookmarks import router as bookmarks_router
from app.api.kb import router as kb_router
from app.api.search import router as search_router

app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(news_router, prefix="/api/v1")
app.include_router(links_router, prefix="/api/v1")
app.include_router(bookmarks_router, prefix="/api/v1")
app.include_router(kb_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")

_AVATARS_DIR = Path("/data/avatars")
_NEWS_MEDIA_DIR = Path("/data/news_media")
_LINK_ICONS_DIR = Path("/data/link_icons")
_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
_NEWS_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
_LINK_ICONS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/media/avatars", StaticFiles(directory=str(_AVATARS_DIR)), name="avatars")
app.mount("/media/news", StaticFiles(directory=str(_NEWS_MEDIA_DIR)), name="news_media")
app.mount("/media/link_icons", StaticFiles(directory=str(_LINK_ICONS_DIR)), name="link_icons")
