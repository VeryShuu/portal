"""История импортов отсутствий ERP (``GET /erp-sync/absences/runs``).

Клон :mod:`runs` (поток дней рождения), отдельная таблица ``erp_absences_runs``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import AdminDep, DbDep, require_erp_sync_module
from app.models.erp_sync import ErpAbsencesRun
from app.schemas.erp_sync import ErpAbsencesRunList, ErpAbsencesRunOut

router = APIRouter(dependencies=[Depends(require_erp_sync_module)])


@router.get("/absences/runs", response_model=ErpAbsencesRunList)
async def list_absences_runs(
    _admin: AdminDep,
    db: DbDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ErpAbsencesRunList:
    """Пагинированный список последних импортов отсутствий (новые первыми).

    ``report`` (JSONB) возвращается как есть — фронтенд рендерит разделы
    inserted/unmatched/ambiguous/errors.
    """
    total = (await db.execute(select(func.count()).select_from(ErpAbsencesRun))).scalar_one()
    rows = (
        (
            await db.execute(
                select(ErpAbsencesRun)
                .order_by(ErpAbsencesRun.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return ErpAbsencesRunList(
        items=[ErpAbsencesRunOut.model_validate(r) for r in rows], total=total
    )


@router.get("/absences/runs/{run_id}", response_model=ErpAbsencesRunOut)
async def get_absences_run(run_id: int, _admin: AdminDep, db: DbDep) -> ErpAbsencesRunOut:
    row = (
        await db.execute(select(ErpAbsencesRun).where(ErpAbsencesRun.id == run_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return ErpAbsencesRunOut.model_validate(row)
