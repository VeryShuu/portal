"""ZIP job lifecycle: create, status, download."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_VIEWER
from app.models.photos import PhotoZipJob
from app.schemas.photos import ZipJobPublic
from app.services import photos_photo_repo
from app.services.photos_acl import require_folder_permission

from ._common import _get_arq, _zip_job_to_public, logger

_ZIPS_INTERNAL_PREFIX = "/internal/photos-zips/"
_ZIPS_ROOT = Path("/data/photos/zips")

router = APIRouter()


@router.post("/folders/{folder_id}/zip", response_model=ZipJobPublic, status_code=201)
async def create_zip_job(
    folder_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> ZipJobPublic:
    folder = await photos_photo_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_VIEWER, db, redis)

    job = PhotoZipJob(folder_id=folder_id, user_id=user.id, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    pool = await _get_arq(request)
    if pool is not None:
        try:
            await pool.enqueue_job(
                "generate_folder_zip",
                str(job.id),
                _job_id=f"photos:zip_job:{job.id}",
            )
        except Exception as exc:
            logger.warning("photos.zip.enqueue_failed", job_id=str(job.id), error=str(exc))

    return _zip_job_to_public(job)


@router.get("/zip-jobs/{job_id}", response_model=ZipJobPublic)
async def get_zip_job(job_id: uuid.UUID, db: DbDep, user: CurrentUser) -> ZipJobPublic:
    job = await photos_photo_repo.fetch_zip_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Zip job not found")
    if user.role != "admin" and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return _zip_job_to_public(job)


@router.get("/zip-jobs/{job_id}/download")
async def download_zip_job(job_id: uuid.UUID, db: DbDep, user: CurrentUser) -> Response:
    job = await photos_photo_repo.fetch_zip_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Zip job not found")
    if user.role != "admin" and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if job.status != "done" or not job.file_path:
        raise HTTPException(status_code=404, detail="File not ready")
    zip_path = Path(job.file_path)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    try:
        rel = zip_path.relative_to(_ZIPS_ROOT)
        accel_path = _ZIPS_INTERNAL_PREFIX + str(rel)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Invalid zip path") from exc
    filename = f"folder-{job.folder_id}.zip"
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": accel_path,
            "Content-Type": "application/zip",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
