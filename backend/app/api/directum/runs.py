"""История прогонов Directum (``GET /directum/runs``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import AdminDep, DbDep, require_directum_module
from app.models.directum import DirectumRun
from app.schemas.directum import DirectumRunList, DirectumRunOut

router = APIRouter(dependencies=[Depends(require_directum_module)])


@router.get("/runs", response_model=DirectumRunList)
async def list_runs(
    _admin: AdminDep,
    db: DbDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> DirectumRunList:
    """Пагинированный список прогонов (новые первыми). ``report`` (JSONB)
    возвращается как есть — фронтенд рендерит разделы."""
    total = (await db.execute(select(func.count()).select_from(DirectumRun))).scalar_one()
    rows = (
        (
            await db.execute(
                select(DirectumRun)
                .order_by(DirectumRun.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return DirectumRunList(items=[DirectumRunOut.model_validate(r) for r in rows], total=total)


@router.get("/runs/{run_id}", response_model=DirectumRunOut)
async def get_run(run_id: int, _admin: AdminDep, db: DbDep) -> DirectumRunOut:
    row = (
        await db.execute(select(DirectumRun).where(DirectumRun.id == run_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return DirectumRunOut.model_validate(row)
