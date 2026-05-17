"""Module-level shared state (caches + config file paths + http client).

All submodules and tests reference these via the keycloak package namespace
(``app.services.keycloak.<name>``), so the dicts must live in exactly one
place and be re-exported. Mutable references stay stable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

# ── JWKS cache ─────────────────────────────────────────────────────────────────
_JWKS_CACHE: dict[str, Any] = {}
_JWKS_CACHE_TTL = 300  # 5 min
_JWKS_VERSION_KEY = "jwks"

# ── Settings cache ────────────────────────────────────────────────────────────
_settings_cache: dict[str, Any] = {}
_SETTINGS_CACHE_TTL = 60  # 1 min — cleared immediately on admin save
_SETTINGS_VERSION_KEY = "keycloak_config"

# ── Settings file paths ───────────────────────────────────────────────────────
_KC_SETTINGS_FILE = Path("/data/secrets/keycloak-settings.json")
_LEGACY_KC_SETTINGS_FILE = Path("/data/branding/keycloak-settings.json")

# ── Shared httpx client (lazy) ────────────────────────────────────────────────
_KC_HTTP_CLIENT: httpx.AsyncClient | None = None
_KC_CLIENT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
