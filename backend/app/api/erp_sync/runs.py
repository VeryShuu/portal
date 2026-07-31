"""История импортов ERP-sync (``GET /erp-sync/runs``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import AdminDep, DbDep, require_erp_sync_module
from app.models.erp_sync import ErpSyncRun
from app.schemas.erp_sync import ErpSyncRunList, ErpSyncRunOut

router = APIRouter(dependencies=[Depends(require_erp_sync_module)])


@router.get("/runs", response_model=ErpSyncRunList)
async def list_runs(
    _admin: AdminDep,
    db: DbDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ErpSyncRunList:
    """Пагинированный список последних импортов (новые первыми).

    ``report`` (JSONB) возвращается как есть — фронтенд рендерит разделы
    changed/unmatched/ambiguous/conflicts/errors.
    """
    total = (await db.execute(select(func.count()).select_from(ErpSyncRun))).scalar_one()
    rows = (
        (
            await db.execute(
                select(ErpSyncRun)
                .order_by(ErpSyncRun.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return ErpSyncRunList(items=[ErpSyncRunOut.model_validate(r) for r in rows], total=total)


@router.get("/runs/{run_id}", response_model=ErpSyncRunOut)
async def get_run(run_id: int, _admin: AdminDep, db: DbDep) -> ErpSyncRunOut:
    row = (await db.execute(select(ErpSyncRun).where(ErpSyncRun.id == run_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return ErpSyncRunOut.model_validate(row)
