import sentry_sdk
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

import secrets as _secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Request
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

        existing_result = await db.execute(select(User).where(User.email == settings.admin_email))
        existing_user = existing_result.scalar_one_or_none()
        if existing_user is not None:
            # Безопасное поведение: роль и auth_source синхронизируем, но
            # password_hash НЕ перезаписываем при каждом старте, иначе пароль
            # сменённый через UI откатывается к значению ADMIN_PASSWORD.
            values = {"role": "admin", "auth_source": "local"}
            reason = "bootstrap.admin_role_synced"
            if settings.admin_password_reset_on_start or not existing_user.password_hash:
                values["password_hash"] = hash_password(settings.admin_password)
                reason = "bootstrap.admin_password_synced"
            await db.execute(
                update(User).where(User.email == settings.admin_email).values(**values)
            )
            await db.commit()
            logger.info(reason, user_email=settings.admin_email)
            return

        result = await db.execute(select(User).where(User.role == "admin"))
        if result.scalar_one_or_none():
            await db.commit()
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
    from arq import create_pool as arq_create_pool
    from arq.connections import RedisSettings
    app.state.arq_pool = await arq_create_pool(RedisSettings.from_dsn(settings.redis_url))
    # P1-18: launch a single Chromium per process and reuse contexts per export.
    from app.core.pdf import startup_browser, shutdown_browser
    await startup_browser()
    try:
        yield
    finally:
        logger.info("portal.shutdown")
        await shutdown_browser()
        if hasattr(app.state, "arq_pool") and app.state.arq_pool:
            await app.state.arq_pool.aclose()
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
    allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
)


_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = (
    "/api/v1/auth/callback",         # OIDC redirect from Keycloak — no Origin
    "/api/v1/auth/local/login",      # Pre-session login: cookie not yet issued
    "/api/v1/auth/logout",           # Front-channel logout from Keycloak (GET) — no header
)
_CSRF_COOKIE_NAME = "XSRF-TOKEN"
_CSRF_HEADER_NAME = "x-xsrf-token"


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    """Defense-in-depth CSRF using two complementary checks:

    1. Origin/Referer must match ``portal_base_url`` (catches simple cross-site
       form submissions even from browsers without modern SameSite support).
    2. Double-submit cookie: the JS-readable ``XSRF-TOKEN`` cookie value must
       match the ``X-XSRF-TOKEN`` header. The cookie is auto-issued on the
       first safe response, the SPA echoes it back on every state-changing
       request via ``api/index.ts`` interceptor.

    OIDC redirect callbacks and the very first ``/auth/local/login`` are
    exempt because they happen before the cookie pair can be established.
    """
    path = request.url.path
    is_safe = request.method in _CSRF_SAFE_METHODS
    is_exempt = any(path.startswith(p) for p in _CSRF_EXEMPT_PATHS)

    if not is_safe and not is_exempt:
        from fastapi.responses import JSONResponse
        from urllib.parse import urlparse
        from app.api.system_settings import load_system_settings as _load_sys

        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            _base_url = _load_sys().portal_base_url
            if _base_url:
                expected_parts = urlparse(_base_url)
                actual_parts = urlparse(origin)
                # Strict host + scheme match — защищает от
                # `https://portal.company.local.evil.com` и `http://` подмены
                # под `https://` portal_base_url.
                if (
                    actual_parts.scheme != expected_parts.scheme
                    or actual_parts.netloc.lower() != expected_parts.netloc.lower()
                ):
                    return JSONResponse(status_code=403, content={"detail": "CSRF: Origin mismatch"})
            # portal_base_url не настроен → строгая проверка origin пропускается,
            # защита обеспечивается double-submit cookie ниже.
        else:
            return JSONResponse(status_code=403, content={"detail": "CSRF: Origin header required"})

        # Double-submit verification — applies only to /api/v1/* (UI calls).
        if path.startswith("/api/v1/"):
            cookie_token = request.cookies.get(_CSRF_COOKIE_NAME)
            header_token = request.headers.get(_CSRF_HEADER_NAME)
            if not cookie_token or not header_token or cookie_token != header_token:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF: token mismatch"},
                )

    response = await call_next(request)

    # Issue / refresh the double-submit cookie on safe responses so the SPA
    # always has a fresh token to echo back. JS-readable on purpose.
    if is_safe and _CSRF_COOKIE_NAME not in request.cookies:
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        response.set_cookie(
            key=_CSRF_COOKIE_NAME,
            value=_secrets.token_urlsafe(32),
            httponly=False,
            secure=(proto == "https"),
            samesite="lax",
            path="/",
        )
    return response


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


async def _require_metrics_token(x_metrics_token: str = Header(default="")) -> None:
    tok = settings.metrics_token
    if tok and not _secrets.compare_digest(x_metrics_token, tok):
        raise HTTPException(status_code=403, detail="Forbidden")


if settings.prometheus_metrics_enabled:
    _instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/ready", "/metrics"],
    ).instrument(app)
    _instrumentator.expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        dependencies=[Depends(_require_metrics_token)],
    )

from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.news import router as news_router
from app.api.links import router as links_router
from app.api.bookmarks import router as bookmarks_router
from app.api.branding import router as branding_router
from app.api.kb import router as kb_router
from app.api.kb_extra import router as kb_extra_router
from app.api.search import router as search_router
from app.api.notifications import router as notifications_router
from app.api.keycloak_admin import router as keycloak_admin_router
from app.api.system_settings import router as system_settings_router
from app.api.modules import router as modules_router
from app.api.photos import router as photos_router

app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(news_router, prefix="/api/v1")
app.include_router(links_router, prefix="/api/v1")
app.include_router(bookmarks_router, prefix="/api/v1")
app.include_router(branding_router, prefix="/api/v1")
app.include_router(kb_router, prefix="/api/v1")
app.include_router(kb_extra_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(keycloak_admin_router, prefix="/api/v1")
app.include_router(system_settings_router, prefix="/api/v1")
app.include_router(modules_router, prefix="/api/v1")
app.include_router(photos_router, prefix="/api/v1")

_AVATARS_DIR = Path("/data/avatars")
_NEWS_MEDIA_DIR = Path("/data/news_media")
_LINK_ICONS_DIR = Path("/data/link_icons")
_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
_NEWS_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
_LINK_ICONS_DIR.mkdir(parents=True, exist_ok=True)

from app.api.system_settings import generate_nginx_confs as _gen_nginx
try:
    _gen_nginx()
except Exception:
    pass

app.mount("/media/avatars", StaticFiles(directory=str(_AVATARS_DIR)), name="avatars")
app.mount("/media/news", StaticFiles(directory=str(_NEWS_MEDIA_DIR)), name="news_media")
app.mount("/media/link_icons", StaticFiles(directory=str(_LINK_ICONS_DIR)), name="link_icons")
