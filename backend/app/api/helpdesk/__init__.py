"""Helpdesk API package — re-exports the combined router.

Весь пакет гейтируется мастер-флагом ``modules.helpdesk.enabled`` (ТЗ §9.1):
dependency ``require_helpdesk_module`` вешается на объединяющий роутер, поэтому
при выключенном модуле любой helpdesk-эндпоинт → 404 (включая settings/agents).
"""

from fastapi import APIRouter, Depends

from app.api.deps import require_helpdesk_module

from .agents import router as agents_router
from .drafts import router as drafts_router
from .media import router as media_router
from .settings import router as settings_router
from .tickets import router as tickets_router
from .users import router as users_router

# Объединяем tickets + agents + media + drafts + users под одним префиксом
# ``/helpdesk`` (родительский ``/api/v1`` добавляется при регистрации в
# ``app/api/__init__.py``). Все суб-роутеры уже несут ``prefix="/helpdesk..."``.
# Module-gate — на всё.
router = APIRouter(dependencies=[Depends(require_helpdesk_module)])
router.include_router(tickets_router)
router.include_router(agents_router)
router.include_router(settings_router)
router.include_router(media_router)
router.include_router(drafts_router)
router.include_router(users_router)

__all__ = ["router"]
