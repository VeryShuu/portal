"""Storage layer for runtime module configuration.

Pure storage + pydantic models for the per-deployment `modules.json`.
Kept free of HTTP / FastAPI imports so that `app.core` and `app.worker`
can read module flags without depending on `app.api.*`.

HTTP DTOs (IN/OUT) and endpoints live in `app.api.modules`.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.core.cache_version import get_version
from app.core.logging import get_logger

logger = get_logger(__name__)

_SETTINGS_DIR = Path("/data/settings")
_MODULES_FILE = _SETTINGS_DIR / "modules.json"

_modules_cache: dict[str, Any] = {}
_CACHE_TTL = 60
_CACHE_VERSION_KEY = "modules"


# ── Internal models (full secrets) ───────────────────────────────────────────


class NextcloudModuleSettings(BaseModel):
    enabled: bool = False


class PhotosModuleSettings(BaseModel):
    enabled: bool = True
    widget_limit: int = Field(default=8, ge=1, le=50)
    max_size_mb: int = Field(default=50, ge=1, le=500)
    allowed_mime: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/heic",
            "image/heif",
            "image/gif",
        ]
    )
    strip_gps: bool = True
    # #B-10: верхняя граница TTL публичных share-ссылок (дни). Хард-капа
    # `le=365` на Field в схемах запросов оставлена как абсолютный предел,
    # но runtime-кап может быть ниже и меняется без передеплоя.
    max_share_ttl_days: int = Field(default=365, ge=1, le=365)


class MeetingsModuleSettings(BaseModel):
    enabled: bool = False
    calendar_start_hour: int = Field(default=8, ge=0, le=23)
    calendar_end_hour: int = Field(default=19, ge=1, le=24)
    max_recurrence_horizon_days: int = Field(default=31, ge=1, le=365)
    min_search_chars: int = Field(default=3, ge=1, le=10)


class DirectoriesModuleSettings(BaseModel):
    enabled: bool = False


class SignatureModuleSettings(BaseModel):
    enabled: bool = False


class HelpdeskModuleSettings(BaseModel):
    enabled: bool = False


class ErpSyncModuleSettings(BaseModel):
    enabled: bool = False


class AllModuleSettings(BaseModel):
    nextcloud: NextcloudModuleSettings = Field(default_factory=NextcloudModuleSettings)
    photos: PhotosModuleSettings = Field(default_factory=PhotosModuleSettings)
    meetings: MeetingsModuleSettings = Field(default_factory=MeetingsModuleSettings)
    directories: DirectoriesModuleSettings = Field(default_factory=DirectoriesModuleSettings)
    signature: SignatureModuleSettings = Field(default_factory=SignatureModuleSettings)
    helpdesk: HelpdeskModuleSettings = Field(default_factory=HelpdeskModuleSettings)
    erp_sync: ErpSyncModuleSettings = Field(default_factory=ErpSyncModuleSettings)


# ── Storage ───────────────────────────────────────────────────────────────────


def load_modules() -> AllModuleSettings:
    now = time.monotonic()
    if _modules_cache.get("data") and now - _modules_cache.get("fetched_at", 0) < _CACHE_TTL:
        return cast(AllModuleSettings, _modules_cache["data"])

    if _MODULES_FILE.exists():
        try:
            data = AllModuleSettings.model_validate_json(_MODULES_FILE.read_text("utf-8"))
            _modules_cache["data"] = data
            _modules_cache["fetched_at"] = now
            return cast(AllModuleSettings, data)
        except Exception as exc:
            logger.warning("modules.settings_parse_failed", path=str(_MODULES_FILE), error=str(exc))

    data = AllModuleSettings()
    _modules_cache["data"] = data
    _modules_cache["fetched_at"] = now
    return data


async def load_modules_shared(redis: Redis) -> AllModuleSettings:
    current_version = await get_version(redis, _CACHE_VERSION_KEY)
    if (
        _modules_cache.get("data")
        and _modules_cache.get("version") == current_version
        and time.monotonic() - _modules_cache.get("fetched_at", 0) < _CACHE_TTL
    ):
        return cast(AllModuleSettings, _modules_cache["data"])

    if _modules_cache.get("version") != current_version:
        _modules_cache.clear()
        # Cross-process invalidation: when any process calls bump_version() on write,
        # the version in Redis changes immediately. On the next request every process
        # calls get_version() here and detects the mismatch → clears its local cache
        # and reloads from disk. Effective stale window ≈ 0 between write and next request.
    data = load_modules()
    _modules_cache["data"] = data
    _modules_cache["fetched_at"] = time.monotonic()
    _modules_cache["version"] = current_version
    return data


def _save_modules(m: AllModuleSettings) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = m.model_dump_json(indent=2).encode("utf-8")
    fd, tmp_path = tempfile.mkstemp(prefix=".modules.", suffix=".json.tmp", dir=str(_SETTINGS_DIR))
    try:
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        with contextlib.suppress(OSError):
            os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, _MODULES_FILE)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    _modules_cache.clear()


def invalidate_modules_cache() -> None:
    _modules_cache.clear()
