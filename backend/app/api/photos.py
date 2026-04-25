"""API модуля фотогалереи (ADR-030/031).

Собственный модуль фотогалереи: иерархия папок + per-folder ACL
(viewer/uploader/manager) + наследование по дереву + локальное хранение
оригиналов и WebP-thumbnail'ов.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path

from arq import ArqRedis
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.api.modules import load_modules
from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder, PhotoFolderPermission
from app.models.user import User
from app.schemas.photos import (
    CreateFolderRequest,
    FolderPublic,
    FolderTree,
    FolderTreeNode,
    GrantPermissionRequest,
    PermissionList,
    PermissionPublic,
    PhotoList,
    PhotoPublic,
    UpdateFolderRequest,
    UpdatePhotoRequest,
    UploadResult,
    UploadResultItem,
)
from app.services import photos_storage
from app.services.audit import push_audit_event
from app.services.photos_acl import (
    filter_accessible_folders,
    invalidate_folder_cache,
    require_folder_permission,
    require_photo_permission,
    resolve_folder_permission,
    resolve_photo_permission,
)

router = APIRouter(prefix="/photos", tags=["photos"])
logger = get_logger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _slugify(text_: str) -> str:
    norm = unicodedata.normalize("NFKD", text_).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", norm).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or "folder"


async def _get_arq(request: Request) -> ArqRedis | None:
    """Получить ARQ-pool. В обычном FastAPI dep его нет, поэтому делаем lazy."""
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is not None:
        return pool
    try:
        from arq.connections import create_pool
        from arq.connections import RedisSettings
        from app.core.config import get_settings as _gs
        s = _gs()
        pool = await create_pool(RedisSettings.from_dsn(s.redis_url))
        request.app.state.arq_pool = pool
        return pool
    except Exception as exc:
        logger.warning("photos.arq_pool_unavailable", error=str(exc))
        return None


async def _enqueue_processing(request: Request, photo_id: uuid.UUID) -> None:
    pool = await _get_arq(request)
    if pool is None:
        return
    try:
        await pool.enqueue_job("process_photo_upload", str(photo_id))
    except Exception as exc:
        logger.warning("photos.enqueue_failed", photo_id=str(photo_id), error=str(exc))


def _folder_to_public(f: PhotoFolder, *, photos_count: int = 0, children_count: int = 0, permission: str | None = None) -> FolderPublic:
    return FolderPublic(
        id=f.id, parent_id=f.parent_id, name=f.name, slug=f.slug, path=f.path,
        description=f.description, cover_photo_id=f.cover_photo_id,
        photos_count=photos_count, children_count=children_count, permission=permission,
        created_at=f.created_at, updated_at=f.updated_at,
    )


def _photo_to_public(p: Photo, folder_path: str | None = None) -> PhotoPublic:
    return PhotoPublic(
        id=p.id, folder_id=p.folder_id, folder_path=folder_path,
        filename=p.filename, original_name=p.original_name, size_bytes=p.size_bytes,
        mime_type=p.mime_type, width=p.width, height=p.height,
        taken_at=p.taken_at, description=p.description, processed=p.processed,
        uploaded_by=p.uploaded_by, created_at=p.created_at,
    )


async def _module_settings():
    return load_modules().photos


# ── Folders ──────────────────────────────────────────────────────────────────

@router.get("/folders/tree", response_model=FolderTree)
async def list_folder_tree(db: DbDep, user: CurrentUser, redis: RedisDep) -> FolderTree:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.deleted_at.is_(None)).order_by(PhotoFolder.path, PhotoFolder.name)
    )
    folders = list(res.scalars().all())
    accessible = await filter_accessible_folders(user, folders, db, redis)
    accessible_ids = {f.id for f in accessible}
    by_id: dict[uuid.UUID, FolderTreeNode] = {}
    perms: dict[uuid.UUID, str | None] = {}
    for f in accessible:
        perms[f.id] = await resolve_folder_permission(user, f, db, redis)
        by_id[f.id] = FolderTreeNode(
            id=f.id, parent_id=f.parent_id, name=f.name, slug=f.slug, path=f.path,
            permission=perms[f.id], children=[],
        )
    roots: list[FolderTreeNode] = []
    for f in accessible:
        node = by_id[f.id]
        if f.parent_id and f.parent_id in by_id:
            by_id[f.parent_id].children.append(node)
        else:
            roots.append(node)
    return FolderTree(items=roots)


@router.get("/folders/{folder_id}", response_model=FolderPublic)
async def get_folder(folder_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep) -> FolderPublic:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    perm = await resolve_folder_permission(user, folder, db, redis)
    if perm is None:
        raise HTTPException(status_code=403, detail="No access")
    pcount = await db.scalar(
        select(func.count(Photo.id)).where(Photo.folder_id == folder_id, Photo.deleted_at.is_(None))
    )
    ccount = await db.scalar(
        select(func.count(PhotoFolder.id)).where(PhotoFolder.parent_id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    return _folder_to_public(folder, photos_count=int(pcount or 0), children_count=int(ccount or 0), permission=perm)


@router.post("/folders", response_model=FolderPublic, status_code=201)
async def create_folder(
    data: CreateFolderRequest, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> FolderPublic:
    parent: PhotoFolder | None = None
    parent_path = ""
    if data.parent_id:
        pres = await db.execute(select(PhotoFolder).where(PhotoFolder.id == data.parent_id, PhotoFolder.deleted_at.is_(None)))
        parent = pres.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        await require_folder_permission(user, parent, "manager", db, redis)
        parent_path = parent.path or parent.slug
    else:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admin can create root folders")

    slug = _slugify(data.name)
    base_slug = slug
    i = 1
    while True:
        exists = await db.scalar(
            select(func.count(PhotoFolder.id)).where(
                PhotoFolder.parent_id == (parent.id if parent else None),
                PhotoFolder.slug == slug,
                PhotoFolder.deleted_at.is_(None),
            )
        )
        if not exists:
            break
        i += 1
        slug = f"{base_slug}-{i}"
        if i > 9999:
            slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
            break

    new_path = f"{parent_path}/{slug}" if parent_path else slug
    folder = PhotoFolder(
        parent_id=parent.id if parent else None,
        name=data.name, slug=slug, path=new_path,
        description=data.description, created_by=user.id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    await push_audit_event(
        redis, event_type="photos.folder_created", user_id=str(user.id), user_email=user.email,
        resource_type="photo_folder", resource_id=str(folder.id), resource_title=folder.name,
        ip_address=request.client.host if request.client else None,
    )
    return _folder_to_public(folder, permission="manager")


@router.patch("/folders/{folder_id}", response_model=FolderPublic)
async def update_folder(
    folder_id: uuid.UUID, data: UpdateFolderRequest, request: Request,
    db: DbDep, user: CurrentUser, redis: RedisDep,
) -> FolderPublic:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "manager", db, redis)

    if data.name is not None:
        folder.name = data.name
    if data.description is not None:
        folder.description = data.description
    if data.cover_photo_id is not None:
        ph = await db.scalar(select(Photo).where(Photo.id == data.cover_photo_id, Photo.folder_id == folder_id))
        if not ph:
            raise HTTPException(status_code=400, detail="Cover photo must belong to this folder")
        folder.cover_photo_id = data.cover_photo_id
    folder.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(folder)
    await invalidate_folder_cache(redis, folder_id)
    return _folder_to_public(folder, permission="manager")


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "manager", db, redis)
    folder.deleted_at = datetime.now(UTC)
    await db.commit()
    await invalidate_folder_cache(redis, folder_id)
    await push_audit_event(
        redis, event_type="photos.folder_deleted", user_id=str(user.id), user_email=user.email,
        resource_type="photo_folder", resource_id=str(folder_id),
    )
    return Response(status_code=204)


# ── Permissions ──────────────────────────────────────────────────────────────

@router.get("/folders/{folder_id}/permissions", response_model=PermissionList)
async def list_folder_permissions(
    folder_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> PermissionList:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "manager", db, redis)
    res2 = await db.execute(
        select(PhotoFolderPermission)
        .where(PhotoFolderPermission.folder_id == folder_id)
        .order_by(PhotoFolderPermission.created_at)
    )
    items = [PermissionPublic.model_validate(p) for p in res2.scalars().all()]
    return PermissionList(items=items)


@router.post("/folders/{folder_id}/permissions", response_model=PermissionPublic, status_code=201)
async def grant_folder_permission(
    folder_id: uuid.UUID, data: GrantPermissionRequest, request: Request,
    db: DbDep, user: CurrentUser, redis: RedisDep,
) -> PermissionPublic:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "manager", db, redis)

    existing_res = await db.execute(
        select(PhotoFolderPermission).where(
            PhotoFolderPermission.folder_id == folder_id,
            PhotoFolderPermission.subject_id == data.subject_id,
        )
    )
    existing = existing_res.scalar_one_or_none()
    if existing:
        existing.permission = data.permission
        existing.subject_name = data.subject_name
        existing.subject_type = data.subject_type
        existing.granted_by = user.id
        await db.commit()
        await db.refresh(existing)
        perm = existing
    else:
        perm = PhotoFolderPermission(
            folder_id=folder_id, subject_type=data.subject_type, subject_id=data.subject_id,
            subject_name=data.subject_name, permission=data.permission, granted_by=user.id,
        )
        db.add(perm)
        await db.commit()
        await db.refresh(perm)
    await invalidate_folder_cache(redis, folder_id)
    await push_audit_event(
        redis, event_type="photos.permission_granted", user_id=str(user.id), user_email=user.email,
        resource_type="photo_folder", resource_id=str(folder_id),
        metadata={"subject_id": data.subject_id, "permission": data.permission},
    )
    return PermissionPublic.model_validate(perm)


@router.delete("/folders/{folder_id}/permissions/{subject_id}", status_code=204)
async def revoke_folder_permission(
    folder_id: uuid.UUID, subject_id: str, request: Request,
    db: DbDep, user: CurrentUser, redis: RedisDep,
) -> Response:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "manager", db, redis)
    await db.execute(
        delete(PhotoFolderPermission).where(
            PhotoFolderPermission.folder_id == folder_id,
            PhotoFolderPermission.subject_id == subject_id,
        )
    )
    await db.commit()
    await invalidate_folder_cache(redis, folder_id)
    await push_audit_event(
        redis, event_type="photos.permission_revoked", user_id=str(user.id), user_email=user.email,
        resource_type="photo_folder", resource_id=str(folder_id),
        metadata={"subject_id": subject_id},
    )
    return Response(status_code=204)


# ── Photos ───────────────────────────────────────────────────────────────────

@router.get("/folders/{folder_id}/photos", response_model=PhotoList)
async def list_folder_photos(
    folder_id: uuid.UUID,
    db: DbDep, user: CurrentUser, redis: RedisDep,
    page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200),
    sort: str = Query("created_at", pattern=r"^(created_at|taken_at|original_name)$"),
) -> PhotoList:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "viewer", db, redis)

    sort_col = {"created_at": Photo.created_at, "taken_at": Photo.taken_at, "original_name": Photo.original_name}[sort]
    base = select(Photo).where(Photo.folder_id == folder_id, Photo.deleted_at.is_(None))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    res2 = await db.execute(
        base.order_by(sort_col.desc().nullslast() if sort != "original_name" else sort_col.asc())
        .offset((page - 1) * per_page).limit(per_page)
    )
    items = [_photo_to_public(p, folder_path=folder.path) for p in res2.scalars().all()]
    return PhotoList(items=items, total=int(total or 0), page=page, per_page=per_page)


@router.get("/recent", response_model=list[PhotoPublic])
async def list_recent_photos(
    db: DbDep, user: CurrentUser, redis: RedisDep,
    limit: int = Query(8, ge=1, le=50),
) -> list[PhotoPublic]:
    cfg = await _module_settings()
    if not cfg.enabled:
        return []
    eff_limit = min(limit, cfg.widget_limit or 8)
    res = await db.execute(
        select(Photo, PhotoFolder)
        .join(PhotoFolder, Photo.folder_id == PhotoFolder.id)
        .where(Photo.deleted_at.is_(None), PhotoFolder.deleted_at.is_(None), Photo.processed.is_(True))
        .order_by(Photo.created_at.desc())
        .limit(eff_limit * 6)  # выгребаем с запасом для ACL-фильтрации
    )
    rows = res.all()
    out: list[PhotoPublic] = []
    for photo, folder in rows:
        if user.role != "admin":
            perm = await resolve_folder_permission(user, folder, db, redis)
            if perm is None:
                continue
        out.append(_photo_to_public(photo, folder_path=folder.path))
        if len(out) >= eff_limit:
            break
    return out


@router.get("/{photo_id}", response_model=PhotoPublic)
async def get_photo(photo_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep) -> PhotoPublic:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, "viewer", db, redis)
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    return _photo_to_public(photo, folder_path=folder.path if folder else None)


@router.patch("/{photo_id}", response_model=PhotoPublic)
async def update_photo(
    photo_id: uuid.UUID, data: UpdatePhotoRequest, db: DbDep, user: CurrentUser, redis: RedisDep
) -> PhotoPublic:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, "uploader", db, redis)
    if data.description is not None:
        photo.description = data.description
    if data.folder_id is not None and data.folder_id != photo.folder_id:
        target = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == data.folder_id, PhotoFolder.deleted_at.is_(None)))
        if not target:
            raise HTTPException(status_code=404, detail="Target folder not found")
        await require_folder_permission(user, target, "uploader", db, redis)
        photo.folder_id = data.folder_id
    await db.commit()
    await db.refresh(photo)
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    return _photo_to_public(photo, folder_path=folder.path if folder else None)


@router.delete("/{photo_id}", status_code=204)
async def delete_photo(
    photo_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    # Автор-uploader или manager папки.
    if photo.uploaded_by != user.id and user.role != "admin":
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder:
            await require_folder_permission(user, folder, "manager", db, redis)
    photo.deleted_at = datetime.now(UTC)
    await db.commit()
    await push_audit_event(
        redis, event_type="photos.photo_deleted", user_id=str(user.id), user_email=user.email,
        resource_type="photo", resource_id=str(photo_id),
    )
    return Response(status_code=204)


# ── Upload ───────────────────────────────────────────────────────────────────

@router.post("/folders/{folder_id}/upload", response_model=UploadResult)
async def upload_photos(
    folder_id: uuid.UUID, request: Request,
    db: DbDep, user: CurrentUser, redis: RedisDep,
    files: list[UploadFile] = File(...),
) -> UploadResult:
    cfg = await _module_settings()
    if not cfg.enabled:
        raise HTTPException(status_code=503, detail="Photos module disabled")

    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "uploader", db, redis)

    max_bytes = (cfg.max_size_mb or 50) * 1024 * 1024
    allowed_mime = set(cfg.allowed_mime or [])
    items: list[UploadResultItem] = []

    for f in files:
        try:
            data = await f.read()
            if len(data) > max_bytes:
                items.append(UploadResultItem(original_name=f.filename or "?", ok=False, error="file too large"))
                continue
            if not photos_storage.is_allowed_ext(f.filename or ""):
                items.append(UploadResultItem(original_name=f.filename or "?", ok=False, error="extension not allowed"))
                continue
            if allowed_mime and f.content_type and f.content_type not in allowed_mime:
                items.append(UploadResultItem(original_name=f.filename or "?", ok=False, error="mime not allowed"))
                continue

            fname, size = photos_storage.save_original(folder.path, f.filename or "photo.bin", data)
            photo = Photo(
                folder_id=folder_id, filename=fname, original_name=f.filename or fname,
                size_bytes=size, mime_type=f.content_type, uploaded_by=user.id,
            )
            db.add(photo)
            await db.commit()
            await db.refresh(photo)
            await _enqueue_processing(request, photo.id)
            await push_audit_event(
                redis, event_type="photos.photo_uploaded", user_id=str(user.id), user_email=user.email,
                resource_type="photo", resource_id=str(photo.id), resource_title=photo.original_name,
                metadata={"folder_id": str(folder_id), "size_bytes": size},
            )
            items.append(UploadResultItem(photo_id=photo.id, original_name=photo.original_name, ok=True))
        except Exception as exc:
            logger.exception("photos.upload_failed", filename=f.filename, error=str(exc))
            items.append(UploadResultItem(original_name=f.filename or "?", ok=False, error=str(exc)))

    return UploadResult(items=items)


# ── File serving (X-Accel-Redirect) ──────────────────────────────────────────

_THUMB_SIZES = {200, 600, 1600}


@router.get("/thumbnail/{photo_id}/{size}")
async def get_thumbnail(
    photo_id: uuid.UUID, size: int, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    if size not in _THUMB_SIZES:
        raise HTTPException(status_code=400, detail="Invalid thumbnail size")
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, "viewer", db, redis)

    thumb_fs = photos_storage.thumb_path(photo_id, size)
    if not thumb_fs.exists():
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder:
            original_path = photos_storage.folder_fs_path(folder.path) / photo.filename
            if original_path.exists():
                try:
                    photos_storage.generate_thumbnails(photo_id, original_path)
                    if not photo.processed:
                        await db.execute(
                            update(Photo).where(Photo.id == photo_id).values(processed=True)
                        )
                        await db.commit()
                except Exception as exc:
                    logger.exception(
                        "photos.thumbnail.fallback_failed",
                        photo_id=str(photo_id),
                        error=str(exc),
                    )
                    raise HTTPException(status_code=500, detail="Thumbnail generation failed") from exc
            else:
                raise HTTPException(status_code=404, detail="Original missing")

    internal = f"/internal/photos-thumbs/{photo_id}/{size}.webp"
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": internal,
            "Content-Type": "image/webp",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/original/{photo_id}")
async def get_original(
    photo_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, "viewer", db, redis)
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder missing")
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", photo.filename)
    internal = f"/internal/photos-originals/{folder.path}/{safe_name}"
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": internal,
            "Content-Type": photo.mime_type or "application/octet-stream",
            "Content-Disposition": f'inline; filename="{safe_name}"',
        },
    )
