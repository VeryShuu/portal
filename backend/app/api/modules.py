import os
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import AdminDep
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["modules"])

_SETTINGS_DIR = Path("/data/settings")
_MODULES_FILE = _SETTINGS_DIR / "modules.json"

_modules_cache: dict[str, Any] = {}
_CACHE_TTL = 60


# ── Internal models (full secrets) ───────────────────────────────────────────


class NextcloudModuleSettings(BaseModel):
    enabled: bool = False


class PhotosModuleSettings(BaseModel):
    enabled: bool = True
    widget_limit: int = Field(default=8, ge=1, le=50)
    max_size_mb: int = Field(default=50, ge=1, le=500)
    allowed_mime: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "image/gif",
        ]
    )
    strip_gps: bool = True


class AllModuleSettings(BaseModel):
    nextcloud: NextcloudModuleSettings = Field(default_factory=NextcloudModuleSettings)
    photos: PhotosModuleSettings = Field(default_factory=PhotosModuleSettings)


# ── OUT models ────────────────────────────────────────────────────────────────


class NextcloudModuleOut(BaseModel):
    enabled: bool


class PhotosModuleOut(BaseModel):
    enabled: bool
    widget_limit: int
    max_size_mb: int
    allowed_mime: list[str]
    strip_gps: bool


class AllModuleSettingsOut(BaseModel):
    nextcloud: NextcloudModuleOut
    photos: PhotosModuleOut


# ── IN models ─────────────────────────────────────────────────────────────────


class NextcloudModuleIn(BaseModel):
    enabled: bool


class PhotosModuleIn(BaseModel):
    enabled: bool = True
    widget_limit: int = Field(default=8, ge=1, le=50)
    max_size_mb: int = Field(default=50, ge=1, le=500)
    allowed_mime: list[str] = Field(default_factory=list)
    strip_gps: bool = True


# ── Storage ───────────────────────────────────────────────────────────────────

def load_modules() -> AllModuleSettings:
    now = time.monotonic()
    if _modules_cache.get("data") and now - _modules_cache.get("fetched_at", 0) < _CACHE_TTL:
        return _modules_cache["data"]

    if _MODULES_FILE.exists():
        try:
            data = AllModuleSettings.model_validate_json(_MODULES_FILE.read_text("utf-8"))
            _modules_cache["data"] = data
            _modules_cache["fetched_at"] = now
            return data
        except Exception as exc:
            logger.warning("modules.settings_parse_failed", path=str(_MODULES_FILE), error=str(exc))

    data = AllModuleSettings()
    _modules_cache["data"] = data
    _modules_cache["fetched_at"] = now
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
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, _MODULES_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    _modules_cache.clear()


def invalidate_modules_cache() -> None:
    _modules_cache.clear()


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _photos_out(m: PhotosModuleSettings) -> PhotosModuleOut:
    return PhotosModuleOut(
        enabled=m.enabled,
        widget_limit=m.widget_limit,
        max_size_mb=m.max_size_mb,
        allowed_mime=list(m.allowed_mime),
        strip_gps=m.strip_gps,
    )


@router.get("/admin/modules", response_model=AllModuleSettingsOut)
async def get_module_settings(_: AdminDep) -> AllModuleSettingsOut:
    m = load_modules()
    return AllModuleSettingsOut(
        nextcloud=NextcloudModuleOut(enabled=m.nextcloud.enabled),
        photos=_photos_out(m.photos),
    )


@router.put("/admin/modules/photos", response_model=PhotosModuleOut)
async def update_photos_module(data: PhotosModuleIn, _: AdminDep) -> PhotosModuleOut:
    m = load_modules()
    updated = PhotosModuleSettings(
        enabled=data.enabled,
        widget_limit=data.widget_limit,
        max_size_mb=data.max_size_mb,
        allowed_mime=data.allowed_mime or m.photos.allowed_mime,
        strip_gps=data.strip_gps,
    )
    m.photos = updated
    _save_modules(m)
    logger.info("modules.photos_updated", enabled=updated.enabled)
    return _photos_out(updated)


@router.put("/admin/modules/nextcloud", response_model=NextcloudModuleOut)
async def update_nextcloud_module(data: NextcloudModuleIn, _: AdminDep) -> NextcloudModuleOut:
    m = load_modules()
    m.nextcloud = NextcloudModuleSettings(enabled=data.enabled)
    _save_modules(m)
    logger.info("modules.nextcloud_updated", enabled=data.enabled)
    return NextcloudModuleOut(enabled=data.enabled)
