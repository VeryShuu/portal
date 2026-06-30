"""Helpdesk API package — re-exports the combined router."""

from fastapi import APIRouter

from .agents import router as agents_router
from .tickets import router as tickets_router

# Объединяем tickets + agents под одним префиксом ``/helpdesk`` (родительский
# ``/api/v1`` добавляется при регистрации в ``app/api/__init__.py``). Оба
# суб-роутера уже несут ``prefix="/helpdesk..."``.
router = APIRouter()
router.include_router(tickets_router)
router.include_router(agents_router)

__all__ = ["router"]
