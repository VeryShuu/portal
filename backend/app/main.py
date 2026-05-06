import json as _json
import os
import secrets as _secrets
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import sentry_sdk
from arq import create_pool as arq_create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import metrics as _metrics_mod
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.limiter import real_ip_identifier
from app.core.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)
from app.core.security import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, hash_password
from app.core.sentry import scrub_sensitive
from app.models.user import User
from app.services.audit_partitions import ensure_partitions as _ensure_partitions
from app.services.keycloak import close_kc_http_client, init_kc_http_client
from app.services.nextcloud import get_nc_service, invalidate_nc_service
from app.services.session import _session_key
from app.worker.tasks.metrics import METRICS_SNAPSHOT_KEY

settings = get_settings()
from app.core.system_config import load_system_settings as _load_sys_startup

_sys_startup = _load_sys_startup()
configure_logging(
    environment=settings.environment,
    log_level=_sys_startup.log_level or settings.log_level,
    service_name="portal-backend",
    force_json=(
        _sys_startup.log_force_json
        if _sys_startup.log_force_json is not None
        else settings.log_force_json
    ),
)
logger = get_logger(__name__)

_sentry_dsn = _sys_startup.sentry_dsn or settings.sentry_dsn
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        before_send=scrub_sensitive,  # type: ignore[arg-type]
        environment=settings.environment,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
    )


_BOOTSTRAP_LOCK_KEY = 0x504F5254414C0001  # stable int64 — 'PORTAL\x00\x01'


async def _bootstrap_admin() -> None:
    """При запуске создаёт первого локального admin, если заданы ADMIN_EMAIL + ADMIN_PASSWORD.

    Защищено pg_try_advisory_lock (session-level, non-blocking) — только один воркер
    из всего пула выполнит bootstrap. Остальные сразу получают False и выходят,
    не дожидаясь завершения первого.
    """
    if not settings.admin_email or not settings.admin_password:
        return
    if not settings.local_auth_enabled:
        return

    async with AsyncSessionLocal() as db:
        lock_result = await db.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _BOOTSTRAP_LOCK_KEY}
        )
        if not lock_result.scalar():
            return

        try:
            existing_result = await db.execute(
                select(User).where(func.lower(User.email) == settings.admin_email.lower())
            )
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
                    if settings.admin_password_reset_on_start:
                        logger.warning(
                            "bootstrap.admin_password_reset_on_start_enabled",
                            user_email=settings.admin_email,
                            note="Disable ADMIN_PASSWORD_RESET_ON_START after first login",
                        )
                await db.execute(
                    update(User)
                    .where(func.lower(User.email) == settings.admin_email.lower())
                    .values(**values)
                )
                await db.commit()
                logger.info(reason, user_email=settings.admin_email)
                return

            result = await db.execute(select(User).where(User.role == "admin"))
            if result.scalar_one_or_none():
                await db.commit()
                return

            now = datetime.now(UTC)
            stmt = (
                pg_insert(User)
                .values(
                    email=settings.admin_email,
                    full_name="Administrator",
                    auth_source="local",
                    password_hash=hash_password(settings.admin_password),
                    role="admin",
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=["email"])
            )
            await db.execute(stmt)
            await db.commit()
            logger.info("bootstrap.admin_created", user_email=settings.admin_email)
        finally:
            with suppress(Exception):
                await db.execute(
                    text("SELECT pg_advisory_unlock(:k)"), {"k": _BOOTSTRAP_LOCK_KEY}
                )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("portal.startup", environment=settings.environment)
    from app.core.system_config import apply_timezone, load_system_settings

    _startup_sys = load_system_settings()
    apply_timezone(_startup_sys.timezone)
    if not _startup_sys.portal_base_url:
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
    except Exception as _redis_err:
        logger.critical("portal.startup_failed.redis", error=str(_redis_err))
        raise RuntimeError(f"Redis unavailable at startup: {_redis_err}") from _redis_err
    await FastAPILimiter.init(app.state.redis, identifier=real_ip_identifier)
    await init_kc_http_client()
    await _bootstrap_admin()
    app.state.arq_pool = await arq_create_pool(RedisSettings.from_dsn(settings.redis_url))
    from app.api.modules import load_modules

    try:
        if load_modules().nextcloud.enabled:
            await get_nc_service().ensure_root()
    except Exception as _nc_err:
        logger.warning("nc.ensure_root_skipped", error=str(_nc_err))
        with suppress(Exception):
            sentry_sdk.capture_exception(_nc_err, tags={"startup_degraded": "nextcloud"})
    app.state.audit_partitions_ok = False
    try:
        _pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _pg_conn = await asyncpg.connect(_pg_url, statement_cache_size=0)
        try:
            _created = await _ensure_partitions(_pg_conn, months_ahead=3)
            if _created:
                logger.info("audit.startup_partitions_created", tables=_created)
        finally:
            await _pg_conn.close()
        app.state.audit_partitions_ok = True
    except Exception as _part_err:
        logger.warning("audit.startup_partitions_failed", error=str(_part_err))
        with suppress(Exception):
            sentry_sdk.capture_exception(_part_err, tags={"startup_degraded": "audit_partitions"})
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


app = FastAPI(
    title="Корпоративный портал",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

from app.middleware.idempotency import IdempotencyMiddleware

app.add_middleware(IdempotencyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.portal_base_url],
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
)


_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = frozenset({
    "/api/v1/auth/callback",
    "/api/v1/auth/logout",
    "/ocs/v2.php/apps/richdocuments/api/v1/federation",
})
_CSRF_ORIGIN_ONLY_PATHS = frozenset({
    "/api/v1/auth/local/login",
})
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

    Fully exempt paths (no checks): OIDC callback, logout, NC federation.
    Origin-only paths (Origin check but no double-submit): local login.
    """
    path = request.url.path
    is_safe = request.method in _CSRF_SAFE_METHODS
    is_exempt = path in _CSRF_EXEMPT_PATHS
    is_origin_only = path in _CSRF_ORIGIN_ONLY_PATHS

    if not is_safe and not is_exempt:
        from app.core.system_config import load_system_settings as _load_sys

        _base_url = _load_sys().portal_base_url
        if not _base_url:
            _base_url = f"{request.url.scheme}://{request.headers.get('host', '')}"

        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            expected_parts = urlparse(_base_url)
            actual_parts = urlparse(origin)
            if (
                actual_parts.scheme != expected_parts.scheme
                or actual_parts.netloc.lower() != expected_parts.netloc.lower()
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF: Origin mismatch"},
                )
        else:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF: Origin header required"},
            )

        # Double-submit verification — applies only to /api/v1/* (UI calls), not origin-only paths.
        if not is_origin_only and path.startswith("/api/v1/"):
            cookie_token = request.cookies.get(_CSRF_COOKIE_NAME)
            header_token = request.headers.get(_CSRF_HEADER_NAME)
            tokens_match = bool(
                cookie_token
                and header_token
                and _secrets.compare_digest(cookie_token, header_token)
            )
            if not tokens_match:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF: token mismatch"},
                )

    response = await call_next(request)

    # Issue / refresh the double-submit cookie on safe responses and on
    # login/callback so the SPA always has a fresh token to echo back.
    if (
        (is_safe or path in {"/api/v1/auth/local/login", "/api/v1/auth/callback"})
        and _CSRF_COOKIE_NAME not in request.cookies
    ):
        response.set_cookie(
            key=_CSRF_COOKIE_NAME,
            value=_secrets.token_urlsafe(32),
            httponly=False,
            secure=settings.is_production,
            samesite="lax",
            path="/",
        )
    return response


def _build_csp_policy() -> str:
    """Build CSP policy with dynamic frame-src derived from system settings.

    frame-src is narrowed to 'self' + the Nextcloud origin (for Collabora iframes)
    + the video gallery origin (for embedded video iframes).
    Falls back to 'self' only if neither URL is configured.
    Uses load_system_settings() which is cached with 60-second TTL.
    """
    from app.core.system_config import load_system_settings

    frame_src_parts = ["'self'"]
    try:
        sys_settings = load_system_settings()
        for url in (sys_settings.nextcloud_url or "", sys_settings.video_gallery_url or ""):
            if url:
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    origin = f"{parsed.scheme}://{parsed.netloc}"
                    if origin not in frame_src_parts:
                        frame_src_parts.append(origin)
    except Exception:
        pass

    frame_src = " ".join(frame_src_parts)
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        f"frame-src {frame_src}; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'"
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # X-XSS-Protection: 0 — отключаем устаревший фильтр XSS в IE/legacy-Chrome,
    # т.к. современные браузеры опираются на CSP, а сам фильтр исторически
    # создавал XS-Leak уязвимости (см. https://blog.sheddow.xyz/css-timing-attack/).
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = _build_csp_policy()
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


_SESSION_EXTEND_PATHS_SKIP = frozenset({"/health", "/ready", "/metrics"})
_SESSION_EXTEND_MIN_INTERVAL = 300  # extend TTL no more than once per 5 minutes per session


@app.middleware("http")
async def session_sliding_window(request: Request, call_next):
    """Extend session TTL on each authenticated request (sliding window).

    Prevents active users from being logged out mid-work after 8 hours.
    Throttled to one Redis call per session per 5 minutes.
    """
    response = await call_next(request)

    if request.url.path in _SESSION_EXTEND_PATHS_SKIP:
        return response

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return response

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return response

    try:
        throttle_key = f"sess_ext_ts:{session_id}"
        last_str = await redis.get(throttle_key)
        now = time.time()
        if last_str is None or now - float(last_str) >= _SESSION_EXTEND_MIN_INTERVAL:
            await redis.expire(_session_key(session_id), SESSION_TTL_SECONDS)
            await redis.setex(throttle_key, _SESSION_EXTEND_MIN_INTERVAL, str(now))
    except Exception:
        pass

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
        clear_request_context()

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    sc = response.status_code

    if sc >= 500:
        log_method = logger.error
    elif sc >= 400:
        log_method = logger.warning
    else:
        from app.core.system_config import load_system_settings as _lss_req

        _slow_ms = _lss_req().log_slow_request_ms
        log_method = logger.warning if elapsed_ms >= _slow_ms else logger.info

    log_method(
        "http.request",
        status_code=sc,
        elapsed_ms=elapsed_ms,
    )
    response.headers["X-Request-Id"] = request_id
    return response


async def _require_metrics_token(x_metrics_token: str = Header(default="")) -> None:
    from app.core.system_config import load_system_settings

    tok = load_system_settings().metrics_token
    if not tok:
        return
    if not _secrets.compare_digest(x_metrics_token, tok):
        raise HTTPException(status_code=403, detail="Forbidden")


if _sys_startup.prometheus_metrics_enabled:
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

    @app.middleware("http")
    async def _hydrate_custom_metrics(request: Request, call_next):
        """Pull the latest snapshot from Redis into Prometheus gauges before scrape."""
        if request.url.path == "/metrics":
            try:
                redis = getattr(request.app.state, "redis", None)
                if redis is not None:
                    raw = await redis.get(METRICS_SNAPSHOT_KEY)
                    if raw:
                        snap = _json.loads(raw)
                        if "audit_queue_depth" in snap:
                            _metrics_mod.audit_queue_depth.set(float(snap["audit_queue_depth"]))
                        if "audit_processing_depth" in snap:
                            _metrics_mod.audit_processing_depth.set(float(snap["audit_processing_depth"]))
                        if "sse_connections" in snap:
                            _metrics_mod.sse_connections.set(float(snap["sse_connections"]))
                        if "active_users_1h" in snap:
                            _metrics_mod.active_users_1h.set(float(snap["active_users_1h"]))
                        if "photo_storage_bytes" in snap:
                            _metrics_mod.photo_storage_bytes.set(float(snap["photo_storage_bytes"]))
                        for status, value in (snap.get("kb_articles_total") or {}).items():
                            _metrics_mod.kb_articles_total.labels(status=status).set(float(value))
                        for status, value in (snap.get("news_published_total") or {}).items():
                            _metrics_mod.news_published_total.labels(status=status).set(float(value))
                        for src, value in (snap.get("users_total") or {}).items():
                            _metrics_mod.users_total.labels(auth_source=src).set(float(value))
            except Exception as exc:  # pragma: no cover - never break /metrics
                logger.warning(
                    "metrics.hydrate_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
        return await call_next(request)


from app.api.analytics import router as analytics_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.bookmarks import router as bookmarks_router
from app.api.branding import router as branding_router
from app.api.files import router as files_router
from app.api.health import router as health_router
from app.api.kb import router as kb_router
from app.api.kb_extra import router as kb_extra_router
from app.api.keycloak_admin import router as keycloak_admin_router
from app.api.links import router as links_router
from app.api.modules import router as modules_router
from app.api.nc_federation import router as nc_federation_router
from app.api.news import router as news_router
from app.api.news_categories import router as news_categories_router
from app.api.notifications import router as notifications_router
from app.api.photos import router as photos_router
from app.api.search import router as search_router
from app.api.system_settings import router as system_settings_router
from app.api.user_attribute_mappings import router as user_attribute_mappings_router
from app.api.users import router as users_router

app.include_router(health_router)
app.include_router(nc_federation_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(news_router, prefix="/api/v1")
app.include_router(news_categories_router, prefix="/api/v1")
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
app.include_router(files_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(user_attribute_mappings_router, prefix="/api/v1")

_DATA_ROOT = Path(os.getenv("DATA_DIR", "/data"))
_AVATARS_DIR = _DATA_ROOT / "avatars"
_NEWS_MEDIA_DIR = _DATA_ROOT / "news_media"
_LINK_ICONS_DIR = _DATA_ROOT / "link_icons"
for _d in (_AVATARS_DIR, _NEWS_MEDIA_DIR, _LINK_ICONS_DIR):
    with suppress(PermissionError, OSError):
        _d.mkdir(parents=True, exist_ok=True)

from app.core.system_config import generate_nginx_confs as _gen_nginx

with suppress(Exception):
    _gen_nginx()


def _safe_mount(path: str, directory: Path, name: str) -> None:
    try:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
        app.mount(path, StaticFiles(directory=str(directory)), name=name)
    except (PermissionError, OSError, RuntimeError):
        pass


_safe_mount("/media/avatars", _AVATARS_DIR, "avatars")
_safe_mount("/media/news", _NEWS_MEDIA_DIR, "news_media")
_safe_mount("/media/link_icons", _LINK_ICONS_DIR, "link_icons")
