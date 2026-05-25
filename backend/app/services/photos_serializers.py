"""DTO-мапперы для модели фотогалереи.

Лежат в `services/`, а не в `api/photos/_common.py`, чтобы сервисный слой
не зависел от api-слоя (см. ревью, находка #21).
"""

from __future__ import annotations

from app.models.photos import Photo, PhotoFolder, PhotoZipJob
from app.schemas.photos import (
    FolderPublic,
    PhotoPublic,
    PhotoPublicAnon,
    ZipJobPublic,
)


def folder_to_public(
    f: PhotoFolder,
    *,
    photos_count: int = 0,
    children_count: int = 0,
    permission: str | None = None,
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


def _resolve_folder_path(
    folder: PhotoFolder | None,
    folder_path: str | None,
) -> str | None:
    """Resolve effective folder path for DTO output (#B-4).

    Accepts either an ORM ``folder`` (preferred — path is derived internally)
    or a precomputed ``folder_path`` string. Callers no longer need to write
    ``folder.path if folder else None`` at every call site.
    """
    if folder_path is not None:
        return folder_path
    if folder is not None:
        return folder.path
    return None


def photo_to_public(
    p: Photo,
    folder: PhotoFolder | None = None,
    *,
    folder_path: str | None = None,
) -> PhotoPublic:
    return PhotoPublic(
        id=p.id,
        folder_id=p.folder_id,
        folder_path=_resolve_folder_path(folder, folder_path),
        filename=p.filename,
        original_name=p.original_name,
        size_bytes=p.size_bytes,
        mime_type=p.mime_type,
        width=p.width,
        height=p.height,
        taken_at=p.taken_at,
        description=p.description,
        processed=p.processed,
        blurhash=getattr(p, "blurhash", None),
        uploaded_by=p.uploaded_by,
        created_at=p.created_at,
    )


def photo_to_public_anon(
    p: Photo,
    folder: PhotoFolder | None = None,
    *,
    folder_path: str | None = None,
) -> PhotoPublicAnon:
    return PhotoPublicAnon(
        id=p.id,
        folder_path=_resolve_folder_path(folder, folder_path),
        original_name=p.original_name,
        size_bytes=p.size_bytes,
        mime_type=p.mime_type,
        width=p.width,
        height=p.height,
        taken_at=p.taken_at,
        description=p.description,
        processed=p.processed,
        blurhash=getattr(p, "blurhash", None),
        created_at=p.created_at,
    )


def zip_job_to_public(job: PhotoZipJob) -> ZipJobPublic:
    download_url = f"/api/v1/photos/zip-jobs/{job.id}/download" if job.status == "done" else None
    return ZipJobPublic(
        id=job.id,
        folder_id=job.folder_id,
        status=job.status,
        created_at=job.created_at,
        expires_at=job.expires_at,
        download_url=download_url,
    )


__all__ = [
    "folder_to_public",
    "photo_to_public",
    "photo_to_public_anon",
    "zip_job_to_public",
]
