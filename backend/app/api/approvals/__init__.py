"""HTTP API модуля «Согласование документов» (docs/wip/erp-approvals.md).

Роутеры:

* :mod:`documents` — документы на согласование текущего пользователя:
  список, карточка, скачивание вложения, согласовать/отклонить/массово.
* :mod:`settings` — ``GET/PUT /approvals/settings`` (singleton, пароль
  write-only) + ``POST /approvals/test`` (проверка подключения, admin-only).

Все endpoints гейтируются ``require_approvals_module`` (deps.py).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.approvals.documents import router as documents_router
from app.api.approvals.settings import router as settings_router

router = APIRouter(tags=["approvals"])
# settings ПЕРВЫМ: GET /approvals/{document_uuid} иначе перехватывает
# GET /approvals/settings («settings» матчится как document_uuid).
router.include_router(settings_router, prefix="/approvals")
router.include_router(documents_router, prefix="/approvals")

__all__ = ["router"]
