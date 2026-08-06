"""ERP-sync HTTP API (docs/wip/erp-sync.md).

Роутеры:

* :mod:`settings` — ``GET/PUT /erp-sync/settings`` (singleton, write-only
  password) + ``POST /erp-sync/test`` (проверка IMAP-логина).
* :mod:`runs` — ``GET /erp-sync/runs`` (история дней рождения) + ``GET /erp-sync/runs/{id}``.
* :mod:`run` — ``POST /erp-sync/run`` (mailbox-trigger дней рождения через ARQ) +
  ``POST /erp-sync/import-file`` (multipart-upload, общий ``run_import``).
* :mod:`absences_runs` — ``GET /erp-sync/absences/runs`` (история отсутствий) +
  ``GET /erp-sync/absences/runs/{id}``.
* :mod:`absences_run` — ``POST /erp-sync/absences/run`` (mailbox-trigger отсутствий) +
  ``POST /erp-sync/absences/import-file`` (multipart-upload отсутствий).

Все endpoints гейтируются ``ErpSyncModuleEnabled`` (deps.py) и ``AdminDep``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.erp_sync.absences_run import router as absences_run_router
from app.api.erp_sync.absences_runs import router as absences_runs_router
from app.api.erp_sync.run import router as run_router
from app.api.erp_sync.runs import router as runs_router
from app.api.erp_sync.settings import router as settings_router

router = APIRouter(prefix="/erp-sync", tags=["erp-sync"])
router.include_router(settings_router)
router.include_router(runs_router)
router.include_router(run_router)
router.include_router(absences_runs_router)
router.include_router(absences_run_router)

__all__ = ["router"]
