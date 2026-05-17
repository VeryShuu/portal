"""Auth API package.

Раньше — монолитный ``app/api/auth.py`` (609 строк). Разложен на
подмодули по ответственности (см. ref.md, пункт 3.1):

- :mod:`._helpers` — приватные хелперы (``_nz``, ``_callback_uri``,
  ``_upsert_user``, ``_resolve_id_token_nonce``, ...).
- :mod:`.oidc` — OIDC Authorization Code + PKCE: ``/auth/login``,
  ``/auth/callback``.
- :mod:`.logout` — ``POST/GET /auth/logout``.
- :mod:`.local` — локальный вход + публичный ``/auth/config``.
- :mod:`.me` — ``/auth/me`` и ``/auth/refresh``.

API-контракты (paths, methods, operationIds) сохранены — проверено
через OpenAPI snapshot.

Для обратной совместимости с существующими тестами и интеграциями
здесь также реэкспортированы исходные имена-привязки
(``push_audit_event``, ``kc_service``, ``parse_jwt_claims``,
``save_session``, ``settings`` и т. д.).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.security import (
    DUMMY_HASH,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    extract_user_data,
    generate_pkce_challenge,
    generate_pkce_verifier,
    generate_session_id,
    generate_state,
    parse_jwt_claims,
    verify_password_async,
)
from app.core.system_config import load_system_settings
from app.services import keycloak as kc_service
from app.services.audit import push_audit_event
from app.services.session import (
    delete_session,
    get_and_delete_pkce_state,
    get_session,
    get_session_from_request,
    save_pkce_state,
    save_session,
)

from ._helpers import (
    _build_session_cookie_response,
    _callback_uri,
    _client_ip,
    _nz,
    _resolve_id_token_nonce,
    _sso_failure_redirect,
    _upsert_user,
    logger,
)
from .local import router as _local_router
from .logout import router as _logout_router
from .me import router as _me_router
from .oidc import router as _oidc_router

settings = get_settings()

router = APIRouter()
router.include_router(_oidc_router)
router.include_router(_logout_router)
router.include_router(_local_router)
router.include_router(_me_router)

__all__ = [
    "DUMMY_HASH",
    "SESSION_COOKIE_NAME",
    "SESSION_TTL_SECONDS",
    "_build_session_cookie_response",
    "_callback_uri",
    "_client_ip",
    "_nz",
    "_resolve_id_token_nonce",
    "_sso_failure_redirect",
    "_upsert_user",
    "delete_session",
    "extract_user_data",
    "generate_pkce_challenge",
    "generate_pkce_verifier",
    "generate_session_id",
    "generate_state",
    "get_and_delete_pkce_state",
    "get_session",
    "get_session_from_request",
    "kc_service",
    "load_system_settings",
    "logger",
    "parse_jwt_claims",
    "push_audit_event",
    "router",
    "save_pkce_state",
    "save_session",
    "settings",
    "verify_password_async",
]
