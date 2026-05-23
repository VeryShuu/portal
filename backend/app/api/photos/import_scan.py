"""Disk import: scan /data/photos/import/ and enqueue thumbnails via ARQ."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import AdminDep
from app.services import photos_storage

from ._common import _get_arq

router = APIRouter()


@router.post("/import/scan")
async def import_scan(request: Request, user: AdminDep) -> dict:
    import_root = photos_storage.IMPORT_ROOT
    if not import_root.exists():
        raise HTTPException(status_code=404, detail="Import directory not found")
    pool = await _get_arq(request)
    if pool is None:
        raise HTTPException(status_code=503, detail="Task queue unavailable")
    job = await pool.enqueue_job(
        "import_scan_run",
        str(user.id),
        _job_id=f"photos:import_scan:{user.id}",
    )
    if job is None:
        return {
            "job_id": f"photos:import_scan:{user.id}",
            "status": "already_queued_or_running",
        }
    return {"job_id": job.job_id, "status": "queued"}


@router.get("/import/scan/status/{job_id}")
async def import_scan_status(job_id: str, request: Request, user: AdminDep) -> dict:
    from arq.jobs import Job, JobStatus

    pool = await _get_arq(request)
    if pool is None:
        raise HTTPException(status_code=503, detail="Task queue unavailable")
    job = Job(job_id=job_id, redis=pool)
    status = await job.status()
    if status == JobStatus.not_found:
        raise HTTPException(status_code=404, detail="Job not found")
    info = await job.info()
    result = info.result if info is not None else None  # type: ignore[attr-defined]
    return {"job_id": job_id, "status": status.value, "result": result}
