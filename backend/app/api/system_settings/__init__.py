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

Имена, которые мокируют тесты
(``app.api.system_settings.push_audit_event`` и
``app.api.system_settings._CERTS_DIR``), реэкспортированы здесь
для обратной совместимости.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.audit import push_audit_event
from app.services.nginx_config import _CERTS_DIR

from ._onboarding import router as _onboarding_router
from ._public import router as _public_router
from ._settings import _ensure_step_ids
from ._settings import router as _settings_router
from ._tls import router as _tls_router

router = APIRouter()
router.include_router(_settings_router)
router.include_router(_onboarding_router)
router.include_router(_tls_router)
router.include_router(_public_router)

__all__ = ["_CERTS_DIR", "_ensure_step_ids", "push_audit_event", "router"]
