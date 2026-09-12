"""System-settings API package.

Раньше — монолитный ``app/api/system_settings.py`` (587 строк).
Разложен на тематические подмодули (см. ref.md, пункт 1.3):

- :mod:`._settings` — основные ``GET/PUT/PATCH /admin/system/settings`` +
  общая ``_apply_settings`` и сборка обновлённой модели.
- :mod:`._onboarding` — публичный ``/portal/onboarding`` и админские
  reset-ы (онбординг / просмотры шагов).
- :mod:`._tls` — TLS-сертификат/ключ, статус и перезагрузка nginx.
- :mod:`._public` — публичные ``/portal/gallery-links``,
  ``/portal/staff-settings`` и статус Nextcloud для админа.

Подмодули эмитят аудит через общий ``_emit_audit`` (фабрика
``make_audit_emitter("system_settings")``); тесты патчат центральный
``app.services.audit.push_audit_event``. Имя ``_CERTS_DIR`` реэкспортировано
здесь (``app.api.system_settings._CERTS_DIR``) для обратной совместимости.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.audit import make_audit_emitter
from app.services.nginx_config import _CERTS_DIR

from ._onboarding import router as _onboarding_router
from ._public import router as _public_router
from ._settings import _ensure_step_ids
from ._settings import router as _settings_router
from ._tls import router as _tls_router

_emit_audit = make_audit_emitter("system_settings")

router = APIRouter()
router.include_router(_settings_router)
router.include_router(_onboarding_router)
router.include_router(_tls_router)
router.include_router(_public_router)

__all__ = ["_CERTS_DIR", "_emit_audit", "_ensure_step_ids", "router"]
