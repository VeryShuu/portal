"""Directum HTTP API (docs/directum.md).

Роутеры:

* :mod:`settings` — ``GET/PUT /directum/settings`` (singleton, пароль write-only)
  + ``POST /directum/test`` (проверка OData-подключения).
* :mod:`runs` — ``GET /directum/runs`` + ``GET /directum/runs/{id}``.
* :mod:`run` — ``POST /directum/run`` (ручной прогон через ARQ).

Все endpoints гейтируются ``require_directum_module`` (deps.py) и ``AdminDep``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.directum.run import router as run_router
from app.api.directum.runs import router as runs_router
from app.api.directum.settings import router as settings_router

router = APIRouter(prefix="/directum", tags=["directum"])
router.include_router(settings_router)
router.include_router(runs_router)
router.include_router(run_router)

__all__ = ["router"]
