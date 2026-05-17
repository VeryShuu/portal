"""Keycloak integration package.

Раньше — монолитный ``app/services/keycloak.py`` (505 строк). Разложен
на подмодули по ответственности (см. ref.md, пункт 3.1):

- :mod:`._state` — общие mutable-кеши и пути файлов настроек.
- :mod:`.http_client` — singleton ``httpx.AsyncClient``.
- :mod:`.settings` — загрузка и кеширование ``_KCSettings``.
- :mod:`.oidc` — OIDC URL'ы и обмен токенов.
- :mod:`.jwks` — кеш JWKS-ключей.
- :mod:`.directory` — Admin API: пользователи / группы.
- :mod:`.tokens` — service-account токены (sync / directory / admin).

Все публичные и приватные имена реэкспортированы — внешние импорты
``from app.services.keycloak import X`` (включая ``patch.object(kc, "_X", ...)``)
остаются совместимыми. Подмодули используют ленивые lookup'ы через
``from app.services import keycloak as _kc`` внутри функций, чтобы тесты,
которые патчат атрибуты на уровне пакета, видели подменённые значения.
"""

from __future__ import annotations

from app.core.cache_version import get_version
from app.core.config import get_settings
from app.core.logging import get_logger

from . import _state
from ._state import (
    _JWKS_CACHE,
    _JWKS_CACHE_TTL,
    _JWKS_VERSION_KEY,
    _KC_CLIENT_TIMEOUT,
    _KC_HTTP_CLIENT,
    _KC_SETTINGS_FILE,
    _LEGACY_KC_SETTINGS_FILE,
    _SETTINGS_CACHE_TTL,
    _SETTINGS_VERSION_KEY,
    _settings_cache,
)
from .directory import (
    get_admin_users,
    get_groups_members_map,
    get_user_groups,
    search_groups,
    search_users,
)
from .http_client import (
    _get_kc_http_client,
    close_kc_http_client,
    init_kc_http_client,
)
from .jwks import get_jwks, invalidate_jwks_cache
from .oidc import (
    _oidc_base,
    exchange_code_for_tokens,
    get_authorization_url,
    get_logout_url,
    get_silent_auth_url,
    refresh_tokens,
)
from .settings import (
    _get_kc_settings,
    _get_kc_settings_async,
    _KCSettings,
    get_kc_settings,
    invalidate_settings_cache,
)
from .tokens import _get_admin_token, _get_directory_token, _get_sync_token

settings = get_settings()
logger = get_logger(__name__)

__all__ = [
    "_JWKS_CACHE",
    "_JWKS_CACHE_TTL",
    "_JWKS_VERSION_KEY",
    "_KC_CLIENT_TIMEOUT",
    "_KC_HTTP_CLIENT",
    "_KC_SETTINGS_FILE",
    "_LEGACY_KC_SETTINGS_FILE",
    "_SETTINGS_CACHE_TTL",
    "_SETTINGS_VERSION_KEY",
    "_KCSettings",
    "_get_admin_token",
    "_get_directory_token",
    "_get_kc_http_client",
    "_get_kc_settings",
    "_get_kc_settings_async",
    "_get_sync_token",
    "_oidc_base",
    "_settings_cache",
    "_state",
    "close_kc_http_client",
    "exchange_code_for_tokens",
    "get_admin_users",
    "get_authorization_url",
    "get_groups_members_map",
    "get_jwks",
    "get_kc_settings",
    "get_logout_url",
    "get_silent_auth_url",
    "get_user_groups",
    "get_version",
    "init_kc_http_client",
    "invalidate_jwks_cache",
    "invalidate_settings_cache",
    "logger",
    "refresh_tokens",
    "search_groups",
    "search_users",
    "settings",
]
