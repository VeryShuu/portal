"""Shared helpers for the photos API sub-package."""

from __future__ import annotations

import re
import unicodedata
import uuid

from arq import ArqRedis
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.modules import load_modules
from app.core.logging import get_logger
from app.core.modules_config import PhotosModuleSettings
from app.models.photos import Photo, PhotoFolder, PhotoZipJob
from app.schemas.photos import (
    FolderPublic,
    PhotoPublic,
    PhotoPublicAnon,
    ZipJobPublic,
)

logger = get_logger(__name__)


def _slugify(text_: str) -> str:
    norm = unicodedata.normalize("NFKD", text_).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", norm).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or "folder"


async def _get_arq(request: Request) -> ArqRedis | None:
    return getattr(request.app.state, "arq_pool", None)


async def _enqueue_processing(request: Request, photo_id: uuid.UUID) -> None:
    pool = await _get_arq(request)
    if pool is None:
        return
    try:
        await pool.enqueue_job(
            "process_photo_upload",
            str(photo_id),
            _job_id=f"photos:process:{photo_id}",
        )
    except Exception as exc:
        logger.warning("photos.enqueue_failed", photo_id=str(photo_id), error=str(exc))


def _folder_to_public(
    f: PhotoFolder, *, photos_count: int = 0, children_count: int = 0, permission: str | None = None
) -> FolderPublic:
    return FolderPublic(
        id=f.id,
        parent_id=f.parent_id,
        name=f.name,
        slug=f.slug,
        path=f.path,
        description=f.description,
        cover_photo_id=f.cover_photo_id,
        photos_count=photos_count,
        children_count=children_count,
        permission=permission,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


def _photo_to_public(p: Photo, folder_path: str | None = None) -> PhotoPublic:
    return PhotoPublic(
        id=p.id,
        folder_id=p.folder_id,
        folder_path=folder_path,
        filename=p.filename,
        original_name=p.original_name,
        size_bytes=p.size_bytes,
        mime_type=p.mime_type,
        width=p.width,
        height=p.height,
        taken_at=p.taken_at,
        description=p.description,
        processed=p.processed,
        uploaded_by=p.uploaded_by,
        created_at=p.created_at,
    )


def _photo_to_public_anon(p: Photo, folder_path: str | None = None) -> PhotoPublicAnon:
    return PhotoPublicAnon(
        id=p.id,
        folder_path=folder_path,
        original_name=p.original_name,
        size_bytes=p.size_bytes,
        mime_type=p.mime_type,
        width=p.width,
        height=p.height,
        taken_at=p.taken_at,
        description=p.description,
        processed=p.processed,
        created_at=p.created_at,
    )


def _module_settings() -> PhotosModuleSettings:
    return load_modules().photos


def _zip_job_to_public(job: PhotoZipJob) -> ZipJobPublic:
    download_url = f"/api/v1/photos/zip-jobs/{job.id}/download" if job.status == "done" else None
    return ZipJobPublic(
        id=job.id,
        folder_id=job.folder_id,
        status=job.status,
        created_at=job.created_at,
        expires_at=job.expires_at,
        download_url=download_url,
    )


async def _would_create_cycle(
    db: AsyncSession, folder_id: uuid.UUID, new_parent_id: uuid.UUID | None
) -> bool:
    """Возвращает True если перемещение папки под new_parent_id создаст цикл."""
    if new_parent_id is None:
        return False
    if new_parent_id == folder_id:
        return True
    current: uuid.UUID | None = new_parent_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if current == folder_id:
            return True
        if current in visited:
            break
        visited.add(current)
        current = await db.scalar(select(PhotoFolder.parent_id).where(PhotoFolder.id == current))
    return False


__all__ = [
    "_enqueue_processing",
    "_folder_to_public",
    "_get_arq",
    "_module_settings",
    "_photo_to_public",
    "_photo_to_public_anon",
    "_slugify",
    "_would_create_cycle",
    "_zip_job_to_public",
    "logger",
]
