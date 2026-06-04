import os
from contextlib import suppress
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.core.logging import configure_logging, get_logger
from app.core.sentry import scrub_sensitive
from app.core.system_config import load_system_settings, migrate_env_to_system_settings

settings = get_settings()
# One-shot migration of legacy env vars → /data/settings/system.json. Must run
# BEFORE the first load_system_settings() so this process picks up migrated
# values immediately. Idempotent on subsequent restarts.
migrate_env_to_system_settings()
_sys_startup = load_system_settings()

configure_logging(
    environment=settings.environment,
    log_level=_sys_startup.log_level,
    service_name="portal-backend",
    force_json=_sys_startup.log_force_json,
)
logger = get_logger(__name__)

_sentry_dsn = _sys_startup.sentry_dsn
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        before_send=scrub_sensitive,  # type: ignore[arg-type]
        environment=settings.environment,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
    )

app = FastAPI(
    title="Корпоративный портал",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

from app.middleware import install_middleware

install_middleware(app)

from app.api import register_routers

register_routers(app)

# Ensure media directories exist on disk so that uploads succeed.
# Static delivery of /media/* is handled by nginx; FastAPI does NOT mount
# these paths in production. Nginx include configs are rendered by the
# `nginx-config` sidecar (see ./nginx/render-config.sh).
_DATA_ROOT = Path(os.getenv("DATA_DIR", "/data"))
_AVATARS_DIR = _DATA_ROOT / "avatars"
_NEWS_MEDIA_DIR = _DATA_ROOT / "news_media"
_LINK_ICONS_DIR = _DATA_ROOT / "link_icons"
_DIRECTORY_AVATARS_DIR = _DATA_ROOT / "directory_avatars"

for _d in (_AVATARS_DIR, _NEWS_MEDIA_DIR, _LINK_ICONS_DIR, _DIRECTORY_AVATARS_DIR):
    with suppress(PermissionError, OSError):
        _d.mkdir(parents=True, exist_ok=True)
