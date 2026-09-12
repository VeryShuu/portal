from __future__ import annotations

from app.core.logging import get_logger

from ._loader import (
    _to_out,
    apply_timezone,
    load_system_settings,
    load_system_settings_shared,
)
from ._migrations import _LEGACY_ENV_MAP, migrate_env_to_system_settings
from ._schemas import (
    GalleryLinksOut,
    OnboardingStep,
    SystemSettings,
    SystemSettingsIn,
    SystemSettingsOut,
    SystemSettingsPatch,
    _SystemSettingsBase,
)
from ._storage import (
    _CACHE_TTL,
    _CACHE_VERSION_KEY,
    _LOG_LEVELS,
    _SECRET_MASK,
    _SETTINGS_DIR,
    _SYSTEM_SETTINGS_FILE,
    _atomic_write,
    _save_system_settings,
    _settings_cache,
    _settings_cache_lock,
    atomic_write,
    invalidate_settings_cache,
)

logger = get_logger(__name__)

__all__ = [
    "_CACHE_TTL",
    "_CACHE_VERSION_KEY",
    "_LEGACY_ENV_MAP",
    "_LOG_LEVELS",
    "_SECRET_MASK",
    "_SETTINGS_DIR",
    "_SYSTEM_SETTINGS_FILE",
    "GalleryLinksOut",
    "OnboardingStep",
    "SystemSettings",
    "SystemSettingsIn",
    "SystemSettingsOut",
    "SystemSettingsPatch",
    "_SystemSettingsBase",
    "_atomic_write",
    "_save_system_settings",
    "_settings_cache",
    "_settings_cache_lock",
    "_to_out",
    "apply_timezone",
    "atomic_write",
    "invalidate_settings_cache",
    "load_system_settings",
    "load_system_settings_shared",
    "logger",
    "migrate_env_to_system_settings",
]
