"""API модуля фотогалереи (ADR-030/031).

Собственный модуль фотогалереи: иерархия папок + per-folder ACL
(viewer/uploader/manager) + наследование по дереву + локальное хранение
оригиналов и WebP-thumbnail'ов.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from arq import ArqRedis
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.api.modules import load_modules
from app.api.system_settings import load_system_settings
from app.core.config import get_settings as _get_settings
from app.core.uploads import stream_upload_to_path
from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder, PhotoFolderPermission, PhotoZipJob, PhotoTag, PhotoTagAssignment, PhotoFolderShareToken
from app.models.user import User
from app.schemas.photos import (
    BulkActionRequest,
    BulkActionResponse,
    CreateFolderRequest,
    CreateTagRequest,
    FolderPublic,
    FolderShareLinkPublic,
    FolderShareLinkRequest,
    FolderSharePublicForList,
    FolderTree,
    FolderTreeNode,
    GrantPermissionRequest,
    MySharesResponse,
    PermissionList,
    PermissionPublic,
    PhotoList,
    PhotoPublic,
    PhotoSharePublicForList,
    SetPhotoTagsRequest,
    TagList,
    TagPublic,
    UpdateFolderRequest,
    UpdatePhotoRequest,
    UploadResult,
    UploadResultItem,
    ZipJobPublic,
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
    return getattr(request.app.state, "arq_pool", None)


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


def _module_settings():
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


async def _would_create_cycle(db: AsyncSession, folder_id: uuid.UUID, new_parent_id: uuid.UUID | None) -> bool:
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
        current = await db.scalar(
            select(PhotoFolder.parent_id).where(PhotoFolder.id == current)
        )
    return False


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
            cover_photo_id=f.cover_photo_id, permission=perms[f.id], children=[],
        )
    roots: list[FolderTreeNode] = []
    for f in accessible:
        node = by_id[f.id]
        if f.parent_id and f.parent_id in by_id:
            by_id[f.parent_id].children.append(node)
        else:
            roots.append(node)
    return FolderTree(items=roots)


@router.get("/folders/deleted", response_model=list[FolderPublic])
async def list_deleted_folders(db: DbDep, user: AdminDep) -> list[FolderPublic]:
    res = await db.execute(
        select(PhotoFolder)
        .where(PhotoFolder.deleted_at.isnot(None))
        .order_by(PhotoFolder.deleted_at.desc())
    )
    folders = res.scalars().all()
    return [_folder_to_public(f, permission="manager") for f in folders]


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

    # fs_path: материализованный путь Unicode-имён, зеркалит структуру на диске
    parent_fs = (parent.fs_path if parent and parent.fs_path else "") or ""
    fs_seg = photos_storage.sanitize_folder_name(data.name)
    # Защита от коллизий имён файловой системы среди sibling-папок
    base_seg = fs_seg
    j = 2
    while True:
        sib_q = await db.execute(
            select(PhotoFolder.fs_path).where(
                PhotoFolder.parent_id == (parent.id if parent else None),
                PhotoFolder.deleted_at.is_(None),
            )
        )
        used_segs = {(p or "").split("/")[-1] for (p,) in sib_q.all()}
        if fs_seg not in used_segs:
            break
        fs_seg = f"{base_seg} ({j})"
        j += 1
        if j > 9999:
            fs_seg = f"{base_seg}-{uuid.uuid4().hex[:8]}"
            break
    new_fs_path = f"{parent_fs}/{fs_seg}" if parent_fs else fs_seg

    folder = PhotoFolder(
        parent_id=parent.id if parent else None,
        name=data.name, slug=slug, path=new_path, fs_path=new_fs_path,
        description=data.description, created_by=user.id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    # Создаём каталог на диске чтобы структура портала зеркалилась файловой системой
    try:
        photos_storage.folder_fs_path(folder.fs_path).mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("photos.folder_mkdir_failed", folder_id=str(folder.id), error=str(exc))
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

    old_fs_path = folder.fs_path or ""
    old_path = folder.path or ""
    rename_dir = False

    # ── Перемещение в другую родительскую папку ───────────────────────────────
    if "parent_id" in data.model_fields_set:
        new_parent_id = data.parent_id

        if new_parent_id == folder.parent_id:
            pass  # без изменений
        else:
            if await _would_create_cycle(db, folder_id, new_parent_id):
                raise HTTPException(status_code=400, detail="Moving folder would create a cycle")

            new_parent: PhotoFolder | None = None
            new_parent_path = ""
            new_parent_fs = ""

            if new_parent_id is not None:
                np_res = await db.execute(
                    select(PhotoFolder).where(
                        PhotoFolder.id == new_parent_id, PhotoFolder.deleted_at.is_(None)
                    )
                )
                new_parent = np_res.scalar_one_or_none()
                if not new_parent:
                    raise HTTPException(status_code=404, detail="New parent folder not found")
                # Проверяем права на новый родитель: admin или manager
                if user.role != "admin":
                    await require_folder_permission(user, new_parent, "manager", db, redis)
                new_parent_path = new_parent.path or new_parent.slug
                new_parent_fs = new_parent.fs_path or ""
            else:
                # Перемещение в корень — только admin
                if user.role != "admin":
                    raise HTTPException(status_code=403, detail="Only admin can move folders to root")

            # Дедупликация slug среди sibling-папок нового родителя
            base_slug = _slugify(folder.name)
            new_slug = base_slug
            i = 1
            while True:
                slug_cnt = await db.scalar(
                    select(func.count(PhotoFolder.id)).where(
                        PhotoFolder.parent_id == new_parent_id,
                        PhotoFolder.slug == new_slug,
                        PhotoFolder.id != folder_id,
                        PhotoFolder.deleted_at.is_(None),
                    )
                )
                if not slug_cnt:
                    break
                i += 1
                new_slug = f"{base_slug}-{i}"
                if i > 9999:
                    new_slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                    break

            # Дедупликация fs_seg среди sibling-папок нового родителя
            fs_seg = photos_storage.sanitize_folder_name(folder.name)
            base_seg = fs_seg
            j = 2
            while True:
                sib_q = await db.execute(
                    select(PhotoFolder.fs_path).where(
                        PhotoFolder.parent_id == new_parent_id,
                        PhotoFolder.id != folder_id,
                        PhotoFolder.deleted_at.is_(None),
                    )
                )
                used_segs = {(p or "").split("/")[-1] for (p,) in sib_q.all()}
                if fs_seg not in used_segs:
                    break
                fs_seg = f"{base_seg} ({j})"
                j += 1
                if j > 9999:
                    fs_seg = f"{base_seg}-{uuid.uuid4().hex[:8]}"
                    break

            new_path = f"{new_parent_path}/{new_slug}" if new_parent_path else new_slug
            new_fs_path = f"{new_parent_fs}/{fs_seg}" if new_parent_fs else fs_seg

            # Каскадный UPDATE path и fs_path для всех потомков
            if old_path:
                esc_path = old_path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                await db.execute(
                    update(PhotoFolder)
                    .where(PhotoFolder.path.like(f"{esc_path}/%", escape="\\"))
                    .values(
                        path=func.concat(new_path, func.substring(PhotoFolder.path, len(old_path) + 1)),
                        fs_path=func.concat(new_fs_path, func.substring(PhotoFolder.fs_path, len(old_fs_path) + 1)),
                    )
                )

            # Физически перемещаем каталог на диске
            if old_fs_path and new_fs_path != old_fs_path:
                try:
                    photos_storage.rename_folder_dir(old_fs_path, new_fs_path)
                except Exception as exc:
                    logger.warning(
                        "photos.folder_move_failed",
                        folder_id=str(folder_id), old=old_fs_path, new=new_fs_path, error=str(exc),
                    )
                    await db.rollback()
                    raise HTTPException(status_code=500, detail="Folder move failed on disk") from exc

            folder.parent_id = new_parent_id
            folder.slug = new_slug
            folder.path = new_path
            folder.fs_path = new_fs_path
            old_fs_path = new_fs_path  # чтобы блок rename ниже не дублировал перемещение

    # ── Переименование ────────────────────────────────────────────────────────
    if data.name is not None and data.name != folder.name:
        folder.name = data.name
        # Пересчёт fs_path с проверкой коллизий среди sibling-папок
        parent_fs = ""
        if folder.parent_id:
            parent_fs_row = await db.scalar(
                select(PhotoFolder.fs_path).where(PhotoFolder.id == folder.parent_id)
            )
            parent_fs = (parent_fs_row or "") or ""
        fs_seg = photos_storage.sanitize_folder_name(data.name)
        base_seg = fs_seg
        j = 2
        while True:
            sib_q = await db.execute(
                select(PhotoFolder.fs_path).where(
                    PhotoFolder.parent_id == folder.parent_id,
                    PhotoFolder.id != folder.id,
                    PhotoFolder.deleted_at.is_(None),
                )
            )
            used_segs = {(p or "").split("/")[-1] for (p,) in sib_q.all()}
            if fs_seg not in used_segs:
                break
            fs_seg = f"{base_seg} ({j})"
            j += 1
            if j > 9999:
                fs_seg = f"{base_seg}-{uuid.uuid4().hex[:8]}"
                break
        new_fs_path = f"{parent_fs}/{fs_seg}" if parent_fs else fs_seg
        if new_fs_path != (folder.fs_path or ""):
            current_fs = folder.fs_path or ""
            folder.fs_path = new_fs_path
            rename_dir = True
            # Каскад на потомков: подменяем prefix
            if current_fs:
                escaped = current_fs.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                await db.execute(
                    update(PhotoFolder)
                    .where(PhotoFolder.fs_path.like(f"{escaped}/%", escape="\\"))
                    .values(fs_path=func.concat(new_fs_path, func.substring(PhotoFolder.fs_path, len(current_fs) + 1)))
                )
            old_fs_path = current_fs
    if data.description is not None:
        folder.description = data.description
    if data.cover_photo_id is not None:
        ph = await db.scalar(select(Photo).where(Photo.id == data.cover_photo_id, Photo.folder_id == folder_id))
        if not ph:
            raise HTTPException(status_code=400, detail="Cover photo must belong to this folder")
        folder.cover_photo_id = data.cover_photo_id
    folder.updated_at = datetime.now(UTC)
    if rename_dir:
        try:
            photos_storage.rename_folder_dir(old_fs_path, folder.fs_path)
        except Exception as exc:
            logger.warning(
                "photos.folder_rename_failed",
                folder_id=str(folder.id), old=old_fs_path, new=folder.fs_path, error=str(exc),
            )
            await db.rollback()
            raise HTTPException(status_code=500, detail="Folder rename failed") from exc
    await db.commit()
    await db.refresh(folder)
    await invalidate_folder_cache(redis, folder_id, db)
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


@router.post("/folders/{folder_id}/restore", response_model=FolderPublic)
async def restore_folder(
    folder_id: uuid.UUID, request: Request, db: DbDep, user: AdminDep, redis: RedisDep
) -> FolderPublic:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.deleted_at is None:
        raise HTTPException(status_code=400, detail="Folder is not deleted")
    folder.deleted_at = None
    # Восстанавливаем прямых потомков
    await db.execute(
        update(PhotoFolder)
        .where(PhotoFolder.parent_id == folder_id, PhotoFolder.deleted_at.isnot(None))
        .values(deleted_at=None)
    )
    await db.commit()
    await db.refresh(folder)
    await invalidate_folder_cache(redis, folder_id, db)
    await push_audit_event(
        redis, event_type="photos.folder_restored", user_id=str(user.id), user_email=user.email,
        resource_type="photo_folder", resource_id=str(folder_id),
    )
    return _folder_to_public(folder, permission="manager")


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


# ── Folder share links ───────────────────────────────────────────────────────

def _resolve_folder_token_sync_check(token_row: PhotoFolderShareToken) -> None:
    now = datetime.now(UTC)
    if token_row.revoked_at is not None or (token_row.expires_at is not None and token_row.expires_at < now):
        raise HTTPException(status_code=410, detail="Share link expired or revoked")


@router.post("/folders/{folder_id}/share", response_model=FolderShareLinkPublic, status_code=201)
async def create_folder_share(
    folder_id: uuid.UUID, data: FolderShareLinkRequest, db: DbDep, user: CurrentUser, redis: RedisDep
) -> FolderShareLinkPublic:
    import secrets as _secrets
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "manager", db, redis)
    token_str = _secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=data.expires_in_days) if data.expires_in_days else None
    tok = PhotoFolderShareToken(folder_id=folder_id, token=token_str, created_by=user.id, expires_at=expires_at)
    db.add(tok)
    await db.commit()
    await db.refresh(tok)
    await push_audit_event(redis, event_type="photos.folder_share_created", user_id=str(user.id), user_email=user.email, resource_type="photo_folder", resource_id=str(folder_id))
    url = f"/photos/public-folder/{token_str}"
    return FolderShareLinkPublic(id=tok.id, folder_id=tok.folder_id, token=tok.token, url=url, created_at=tok.created_at, expires_at=tok.expires_at)


@router.get("/folders/{folder_id}/shares", response_model=list[FolderShareLinkPublic])
async def list_folder_shares(
    folder_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> list[FolderShareLinkPublic]:
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "manager", db, redis)
    res = await db.execute(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.folder_id == folder_id)
        .order_by(PhotoFolderShareToken.created_at.desc())
    )
    result = []
    for tok in res.scalars().all():
        result.append(FolderShareLinkPublic(
            id=tok.id, folder_id=tok.folder_id, token=tok.token,
            url=f"/photos/public-folder/{tok.token}", created_at=tok.created_at, expires_at=tok.expires_at,
        ))
    return result


# ── Photos ───────────────────────────────────────────────────────────────────

@router.get("/folders/{folder_id}/photos", response_model=PhotoList)
async def list_folder_photos(
    folder_id: uuid.UUID,
    db: DbDep, user: CurrentUser, redis: RedisDep,
    page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200),
    sort: str = Query("created_at", pattern=r"^(created_at|taken_at|original_name)$"),
    min_date: datetime | None = Query(default=None),
    max_date: datetime | None = Query(default=None),
    min_size: int | None = Query(default=None, ge=0),
    max_size: int | None = Query(default=None, ge=0),
    mime_type: str | None = Query(default=None),
) -> PhotoList:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "viewer", db, redis)

    sort_col = {"created_at": Photo.created_at, "taken_at": Photo.taken_at, "original_name": Photo.original_name}[sort]
    base = select(Photo).where(Photo.folder_id == folder_id, Photo.deleted_at.is_(None))
    if min_date is not None:
        base = base.where(Photo.taken_at.isnot(None), Photo.taken_at >= min_date)
    if max_date is not None:
        base = base.where(Photo.taken_at.isnot(None), Photo.taken_at <= max_date)
    if min_size is not None:
        base = base.where(Photo.size_bytes >= min_size)
    if max_size is not None:
        base = base.where(Photo.size_bytes <= max_size)
    if mime_type is not None:
        base = base.where(Photo.mime_type == mime_type)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    res2 = await db.execute(
        base.order_by(sort_col.desc().nullslast() if sort != "original_name" else sort_col.asc())
        .offset((page - 1) * per_page).limit(per_page)
    )
    items = [_photo_to_public(p, folder_path=folder.path) for p in res2.scalars().all()]
    return PhotoList(items=items, total=int(total or 0), page=page, per_page=per_page)


@router.get("/deleted", response_model=PhotoList)
async def list_deleted_photos(
    db: DbDep, user: CurrentUser, redis: RedisDep,
    page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200),
) -> PhotoList:
    cutoff = datetime.now(UTC) - timedelta(days=30)
    base = select(Photo).where(
        Photo.deleted_at.isnot(None),
        Photo.deleted_at > cutoff,
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    res = await db.execute(
        base.order_by(Photo.deleted_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    all_photos = res.scalars().all()
    items: list[PhotoPublic] = []
    for photo in all_photos:
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder is None:
            continue
        if user.role != "admin":
            perm = await resolve_folder_permission(user, folder, db, redis)
            if perm is None:
                continue
        items.append(_photo_to_public(photo, folder_path=folder.path if folder else None))
    return PhotoList(items=items, total=int(total or 0), page=page, per_page=per_page)


@router.get("/recent", response_model=list[PhotoPublic])
async def list_recent_photos(
    db: DbDep, user: CurrentUser, redis: RedisDep,
    limit: int = Query(8, ge=1, le=50),
) -> list[PhotoPublic]:
    cfg = _module_settings()
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


# ── Tags ─────────────────────────────────────────────────────────────────────

@router.get("/tags", response_model=TagList)
async def list_tags(db: DbDep, user: CurrentUser, q: str = Query(default="", max_length=100)) -> TagList:
    stmt = (
        select(PhotoTag, func.count(PhotoTagAssignment.photo_id).label("usage_count"))
        .outerjoin(PhotoTagAssignment, PhotoTagAssignment.tag_id == PhotoTag.id)
        .group_by(PhotoTag.id)
        .order_by(PhotoTag.name)
    )
    if q:
        stmt = stmt.where(PhotoTag.name.ilike(f"%{q}%"))
    res = await db.execute(stmt)
    items = [
        TagPublic(id=row.PhotoTag.id, name=row.PhotoTag.name, slug=row.PhotoTag.slug, usage_count=row.usage_count or 0)
        for row in res.all()
    ]
    return TagList(items=items)


@router.post("/tags", response_model=TagPublic, status_code=201)
async def create_tag(data: CreateTagRequest, db: DbDep, user: CurrentUser) -> TagPublic:
    if user.role not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Editor or admin required")
    slug = _slugify(data.name)
    existing = await db.scalar(select(PhotoTag).where(PhotoTag.name == data.name))
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")
    tag = PhotoTag(name=data.name, slug=slug)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return TagPublic(id=tag.id, name=tag.name, slug=tag.slug, usage_count=0)


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: uuid.UUID, db: DbDep, user: AdminDep) -> Response:
    await db.execute(delete(PhotoTag).where(PhotoTag.id == tag_id))
    await db.commit()
    return Response(status_code=204)


# ── Storage stats ─────────────────────────────────────────────────────────────

@router.get("/storage-stats")
async def get_storage_stats(db: DbDep, user: AdminDep) -> dict:
    res = await db.execute(
        select(
            PhotoFolder.id, PhotoFolder.name, PhotoFolder.path,
            func.coalesce(func.sum(Photo.size_bytes), 0).label("size_bytes"),
            func.count(Photo.id).label("file_count"),
        )
        .join(Photo, Photo.folder_id == PhotoFolder.id)
        .where(Photo.deleted_at.is_(None), PhotoFolder.deleted_at.is_(None))
        .group_by(PhotoFolder.id, PhotoFolder.name, PhotoFolder.path)
        .order_by(func.sum(Photo.size_bytes).desc())
        .limit(50)
    )
    rows = res.all()
    top_folders = [
        {"folder_id": str(r[0]), "folder_name": r[1], "folder_path": r[2], "size_bytes": int(r[3]), "file_count": int(r[4])}
        for r in rows
    ]
    total_size = sum(f["size_bytes"] for f in top_folders)
    total_files = sum(f["file_count"] for f in top_folders)
    return {"total_size_bytes": total_size, "total_files": total_files, "top_folders": top_folders}


# ── My shares ─────────────────────────────────────────────────────────────────

@router.get("/my-shares", response_model=MySharesResponse)
async def get_my_shares(db: DbDep, user: CurrentUser) -> MySharesResponse:
    from app.models.photos import PhotoShareToken
    now = datetime.now(UTC)
    res_photo = await db.execute(
        select(PhotoShareToken).where(
            PhotoShareToken.created_by == user.id,
            PhotoShareToken.revoked_at.is_(None),
        ).order_by(PhotoShareToken.created_at.desc())
    )
    photo_tokens = []
    for tok in res_photo.scalars().all():
        if tok.expires_at and tok.expires_at < now:
            continue
        photo_tokens.append(PhotoSharePublicForList(
            id=tok.id, photo_id=tok.photo_id, token=tok.token,
            url=f"/p/{tok.token}", created_at=tok.created_at, expires_at=tok.expires_at,
        ))
    res_folder = await db.execute(
        select(PhotoFolderShareToken, PhotoFolder.name)
        .join(PhotoFolder, PhotoFolderShareToken.folder_id == PhotoFolder.id)
        .where(
            PhotoFolderShareToken.created_by == user.id,
            PhotoFolderShareToken.revoked_at.is_(None),
        ).order_by(PhotoFolderShareToken.created_at.desc())
    )
    folder_tokens = []
    for row in res_folder.all():
        tok = row[0]
        folder_name = row[1]
        if tok.expires_at and tok.expires_at < now:
            continue
        folder_tokens.append(FolderSharePublicForList(
            id=tok.id, folder_id=tok.folder_id, token=tok.token,
            url=f"/photos/public-folder/{tok.token}", folder_name=folder_name,
            created_at=tok.created_at, expires_at=tok.expires_at,
        ))
    return MySharesResponse(photo_tokens=photo_tokens, folder_tokens=folder_tokens)


@router.delete("/my-shares/photo/{token_id}", status_code=204)
async def revoke_photo_share(token_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep) -> Response:
    from app.models.photos import PhotoShareToken
    tok = await db.scalar(select(PhotoShareToken).where(PhotoShareToken.id == token_id))
    if not tok:
        raise HTTPException(status_code=404, detail="Token not found")
    if tok.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    tok.revoked_at = datetime.now(UTC)
    await db.commit()
    await push_audit_event(redis, event_type="photos.share_revoked", user_id=str(user.id), user_email=user.email, resource_type="photo_share_token", resource_id=str(token_id))
    return Response(status_code=204)


@router.delete("/my-shares/folder/{token_id}", status_code=204)
async def revoke_folder_share(token_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep) -> Response:
    tok = await db.scalar(select(PhotoFolderShareToken).where(PhotoFolderShareToken.id == token_id))
    if not tok:
        raise HTTPException(status_code=404, detail="Token not found")
    if tok.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    tok.revoked_at = datetime.now(UTC)
    await db.commit()
    await push_audit_event(redis, event_type="photos.folder_share_revoked", user_id=str(user.id), user_email=user.email, resource_type="folder_share_token", resource_id=str(token_id))
    return Response(status_code=204)


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
        if not folder:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        await require_folder_permission(user, folder, "manager", db, redis)
    photo.deleted_at = datetime.now(UTC)
    await db.commit()
    await push_audit_event(
        redis, event_type="photos.photo_deleted", user_id=str(user.id), user_email=user.email,
        resource_type="photo", resource_id=str(photo_id),
    )
    return Response(status_code=204)


@router.post("/{photo_id}/restore", response_model=PhotoPublic)
async def restore_photo(
    photo_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> PhotoPublic:
    res = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.deleted_at is None:
        raise HTTPException(status_code=400, detail="Photo is not deleted")
    # Требует uploader+ (автор) или admin
    if user.role != "admin" and photo.uploaded_by != user.id:
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder:
            await require_folder_permission(user, folder, "uploader", db, redis)
        else:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    photo.deleted_at = None
    await db.commit()
    await db.refresh(photo)
    await push_audit_event(
        redis, event_type="photos.photo_restored", user_id=str(user.id), user_email=user.email,
        resource_type="photo", resource_id=str(photo_id),
    )
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    return _photo_to_public(photo, folder_path=folder.path if folder else None)


@router.delete("/{photo_id}/purge", status_code=204)
async def purge_photo(
    photo_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    """Окончательно удаляет фото из корзины (файлы + запись в БД)."""
    res = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.deleted_at is None:
        raise HTTPException(status_code=400, detail="Photo is not in trash")
    if user.role != "admin" and photo.uploaded_by != user.id:
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder:
            await require_folder_permission(user, folder, "manager", db, redis)
        else:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    original: Path | None = None
    if folder:
        original = photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
    photos_storage.delete_photo_files(original, photo.id)
    await db.execute(delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == photo_id))
    await db.execute(delete(Photo).where(Photo.id == photo_id))
    await db.commit()
    await push_audit_event(
        redis, event_type="photos.photo_purged", user_id=str(user.id), user_email=user.email,
        resource_type="photo", resource_id=str(photo_id),
        ip_address=request.client.host if request.client else None,
    )
    return Response(status_code=204)


@router.post("/trash/empty", status_code=200)
async def empty_trash(
    request: Request, db: DbDep, user: AdminDep, redis: RedisDep
) -> dict:
    """Окончательно удаляет ВСЕ фото из корзины (только admin)."""
    res = await db.execute(
        select(Photo).where(Photo.deleted_at.isnot(None))
    )
    photos_to_purge = res.scalars().all()
    purged = 0
    for photo in photos_to_purge:
        try:
            folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
            original: Path | None = None
            if folder:
                original = photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
            photos_storage.delete_photo_files(original, photo.id)
            await db.execute(delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == photo.id))
            purged += 1
        except Exception as exc:
            logger.warning("photos.trash.empty_failed", photo_id=str(photo.id), error=str(exc))
    await db.execute(delete(Photo).where(Photo.deleted_at.isnot(None)))
    await db.commit()
    await push_audit_event(
        redis, event_type="photos.trash_emptied", user_id=str(user.id), user_email=user.email,
        resource_type="photo", resource_id="all",
        ip_address=request.client.host if request.client else None,
    )
    return {"purged": purged}


# ── Photo tags ───────────────────────────────────────────────────────────────

@router.get("/{photo_id}/tags", response_model=list[TagPublic])
async def get_photo_tags(photo_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep) -> list[TagPublic]:
    res_photo = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res_photo.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, "viewer", db, redis)
    res = await db.execute(
        select(PhotoTag)
        .join(PhotoTagAssignment, PhotoTagAssignment.tag_id == PhotoTag.id)
        .where(PhotoTagAssignment.photo_id == photo_id)
        .order_by(PhotoTag.name)
    )
    return [TagPublic(id=t.id, name=t.name, slug=t.slug) for t in res.scalars().all()]


@router.patch("/{photo_id}/tags", response_model=list[TagPublic])
async def set_photo_tags(photo_id: uuid.UUID, data: SetPhotoTagsRequest, db: DbDep, user: CurrentUser, redis: RedisDep) -> list[TagPublic]:
    res_photo = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res_photo.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, "uploader", db, redis)
    await db.execute(delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == photo_id))
    for tag_id in data.tag_ids:
        tag_exists = await db.scalar(select(PhotoTag).where(PhotoTag.id == tag_id))
        if tag_exists:
            db.add(PhotoTagAssignment(photo_id=photo_id, tag_id=tag_id))
    await db.commit()
    res = await db.execute(
        select(PhotoTag)
        .join(PhotoTagAssignment, PhotoTagAssignment.tag_id == PhotoTag.id)
        .where(PhotoTagAssignment.photo_id == photo_id)
        .order_by(PhotoTag.name)
    )
    return [TagPublic(id=t.id, name=t.name, slug=t.slug) for t in res.scalars().all()]


# ── Bulk-операции ─────────────────────────────────────────────────────────────

@router.post("/bulk", response_model=BulkActionResponse)
async def bulk_action(
    data: BulkActionRequest, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> BulkActionResponse:
    processed = 0
    errors: list[str] = []

    target_folder: PhotoFolder | None = None
    if data.action == "move":
        if data.target_folder_id is None:
            raise HTTPException(status_code=400, detail="target_folder_id required for move")
        tf_res = await db.execute(
            select(PhotoFolder).where(
                PhotoFolder.id == data.target_folder_id, PhotoFolder.deleted_at.is_(None)
            )
        )
        target_folder = tf_res.scalar_one_or_none()
        if not target_folder:
            raise HTTPException(status_code=404, detail="Target folder not found")
        if user.role != "admin":
            await require_folder_permission(user, target_folder, "uploader", db, redis)

    for photo_id in data.photo_ids:
        try:
            ph_res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
            photo = ph_res.scalar_one_or_none()
            if not photo:
                errors.append(f"{photo_id}: not found")
                continue

            src_folder_res = await db.execute(
                select(PhotoFolder).where(PhotoFolder.id == photo.folder_id)
            )
            src_folder = src_folder_res.scalar_one_or_none()

            if user.role != "admin":
                if src_folder:
                    src_perm = await resolve_folder_permission(user, src_folder, db, redis)
                else:
                    src_perm = None
                if not src_perm:
                    errors.append(f"{photo_id}: no access to source folder")
                    continue

            if data.action == "delete":
                if user.role != "admin":
                    from app.services.photos_acl import perm_gte
                    perm = await resolve_photo_permission(user, photo, db, redis)
                    if not perm_gte(perm, "uploader"):
                        errors.append(f"{photo_id}: insufficient permissions")
                        continue
                photo.deleted_at = datetime.now(UTC)
                processed += 1

            elif data.action == "move" and target_folder is not None:
                if user.role != "admin":
                    from app.services.photos_acl import perm_gte
                    src_perm = await resolve_photo_permission(user, photo, db, redis)
                    if not perm_gte(src_perm, "uploader"):
                        errors.append(f"{photo_id}: insufficient permissions in source folder")
                        continue

                # Перемещаем файл на диске
                if src_folder:
                    import shutil as _shutil
                    src_dir = photos_storage.folder_fs_path(src_folder.fs_path or src_folder.path)
                    dst_dir = photos_storage.folder_fs_path(target_folder.fs_path or target_folder.path)
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    src_file = src_dir / photo.filename
                    dst_file = dst_dir / photo.filename
                    if src_file.exists() and not dst_file.exists():
                        _shutil.move(str(src_file), str(dst_file))
                    elif src_file.exists() and dst_file.exists():
                        stem = Path(photo.filename).stem
                        ext = Path(photo.filename).suffix
                        candidate = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
                        _shutil.move(str(src_file), str(dst_dir / candidate))
                        photo.filename = candidate

                photo.folder_id = data.target_folder_id
                processed += 1

        except Exception as exc:
            errors.append(f"{photo_id}: {exc}")

    await db.commit()
    return BulkActionResponse(processed=processed, errors=errors)


# ── Upload ───────────────────────────────────────────────────────────────────

@router.post("/folders/{folder_id}/upload", response_model=UploadResult)
async def upload_photos(
    folder_id: uuid.UUID, request: Request,
    db: DbDep, user: CurrentUser, redis: RedisDep,
    files: list[UploadFile] = File(...),
) -> UploadResult:
    cfg = _module_settings()
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
        final_path: Path | None = None
        try:
            if not photos_storage.is_allowed_ext(f.filename or ""):
                items.append(UploadResultItem(original_name=f.filename or "?", ok=False, error="extension not allowed"))
                continue
            effective_ct = f.content_type or ""
            if allowed_mime and effective_ct not in allowed_mime:
                items.append(UploadResultItem(original_name=f.filename or "?", ok=False, error="mime not allowed"))
                continue

            target_dir = photos_storage.folder_fs_path(folder.fs_path or folder.path)
            target_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = target_dir / f"_tmp_{uuid.uuid4().hex}"
            written, _detected = await stream_upload_to_path(f, tmp_path, max_size=max_bytes)
            safe = photos_storage.sanitize_filename(f.filename or "photo.bin")
            stem, ext = Path(safe).stem, (Path(safe).suffix.lower() or ".bin")
            fname = safe
            idx = 1
            while (target_dir / fname).exists():
                fname = f"{stem}-{idx}{ext}"
                idx += 1
                if idx > 9999:
                    fname = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
                    break
            final_path = target_dir / fname
            tmp_path.rename(final_path)
            size = written

            try:
                photo = Photo(
                    folder_id=folder_id, filename=fname, original_name=f.filename or fname,
                    size_bytes=size, mime_type=effective_ct or None, uploaded_by=user.id,
                )
                db.add(photo)
                await db.commit()
                await db.refresh(photo)
            except Exception:
                try:
                    final_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise
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


# ── ZIP-скачивание папки ─────────────────────────────────────────────────────

@router.post("/folders/{folder_id}/zip", response_model=ZipJobPublic, status_code=201)
async def create_zip_job(
    folder_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> ZipJobPublic:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None)))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, "viewer", db, redis)

    job = PhotoZipJob(folder_id=folder_id, user_id=user.id, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    pool = await _get_arq(request)
    if pool is not None:
        try:
            await pool.enqueue_job("generate_folder_zip", str(job.id))
        except Exception as exc:
            logger.warning("photos.zip.enqueue_failed", job_id=str(job.id), error=str(exc))

    return _zip_job_to_public(job)


@router.get("/zip-jobs/{job_id}", response_model=ZipJobPublic)
async def get_zip_job(
    job_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ZipJobPublic:
    res = await db.execute(select(PhotoZipJob).where(PhotoZipJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Zip job not found")
    if user.role != "admin" and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return _zip_job_to_public(job)


@router.get("/zip-jobs/{job_id}/download")
async def download_zip_job(
    job_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> FileResponse:
    res = await db.execute(select(PhotoZipJob).where(PhotoZipJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Zip job not found")
    if user.role != "admin" and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if job.status != "done" or not job.file_path:
        raise HTTPException(status_code=404, detail="File not ready")
    zip_path = Path(job.file_path)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"folder-{job.folder_id}.zip",
    )


# ── Импорт с диска ────────────────────────────────────────────────────────────

@router.post("/import/scan")
async def import_scan(request: Request, db: DbDep, user: AdminDep, redis: RedisDep) -> dict:
    import os

    import_root = photos_storage.IMPORT_ROOT
    if not import_root.exists():
        raise HTTPException(status_code=404, detail="Import directory not found")

    folders_created = 0
    photos_imported = 0
    skipped = 0
    errors: list[str] = []

    # Кэш: абсолютный путь папки → PhotoFolder объект
    folder_cache: dict[str, PhotoFolder] = {}
    # Набор абсолютных путей новых папок (созданных в этом запросе)
    new_folder_paths: set[str] = set()

    async def _get_or_create_folder(abs_dir: Path) -> PhotoFolder | None:
        abs_str = str(abs_dir)
        if abs_str in folder_cache:
            return folder_cache[abs_str]

        rel = abs_dir.relative_to(import_root)
        parts = list(rel.parts)
        if not parts:
            return None

        parent_folder: PhotoFolder | None = None
        if len(parts) > 1:
            parent_folder = await _get_or_create_folder(abs_dir.parent)
            if parent_folder is None:
                return None

        name = abs_dir.name
        slug = _slugify(name)
        parent_id = parent_folder.id if parent_folder else None
        parent_path = (parent_folder.path or parent_folder.slug) if parent_folder else ""

        # Ищем существующую папку по fs_path (хранится как абсолютный путь)
        existing = await db.scalar(
            select(PhotoFolder).where(PhotoFolder.fs_path == abs_str)
        )
        if existing:
            folder_cache[abs_str] = existing
            return existing

        # Дедупликация slug среди sibling-папок
        base_slug = slug
        i = 1
        while True:
            cnt = await db.scalar(
                select(func.count(PhotoFolder.id)).where(
                    PhotoFolder.parent_id == parent_id,
                    PhotoFolder.slug == slug,
                    PhotoFolder.deleted_at.is_(None),
                )
            )
            if not cnt:
                break
            i += 1
            slug = f"{base_slug}-{i}"
            if i > 9999:
                slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                break

        new_path = f"{parent_path}/{slug}" if parent_path else slug
        new_folder = PhotoFolder(
            parent_id=parent_id,
            name=name,
            slug=slug,
            path=new_path,
            fs_path=abs_str,
            created_by=user.id,
        )
        db.add(new_folder)
        await db.flush()
        new_folder_paths.add(abs_str)
        folder_cache[abs_str] = new_folder
        return new_folder

    for dirpath, dirnames, filenames in os.walk(str(import_root)):
        dirnames.sort()
        abs_dir = Path(dirpath)
        if abs_dir == import_root:
            continue

        try:
            folder = await _get_or_create_folder(abs_dir)
            if folder is None:
                continue
            if str(abs_dir) in new_folder_paths:
                folders_created += 1
        except Exception as exc:
            errors.append(f"folder {dirpath}: {exc}")
            continue

        for filename in sorted(filenames):
            if not photos_storage.is_allowed_ext(filename):
                skipped += 1
                continue
            try:
                folder = folder_cache.get(str(abs_dir))
                if folder is None:
                    skipped += 1
                    continue
                existing_photo = await db.scalar(
                    select(func.count(Photo.id)).where(
                        Photo.folder_id == folder.id,
                        Photo.filename == filename,
                    )
                )
                if existing_photo:
                    skipped += 1
                    continue
                file_size = (abs_dir / filename).stat().st_size
                photo = Photo(
                    folder_id=folder.id,
                    filename=filename,
                    original_name=filename,
                    size_bytes=file_size,
                    uploaded_by=user.id,
                )
                db.add(photo)
                await db.flush()
                await _enqueue_processing(request, photo.id)
                photos_imported += 1
            except Exception as exc:
                errors.append(f"{dirpath}/{filename}: {exc}")

    await db.commit()
    logger.info(
        "photos.import.done",
        folders_created=folders_created,
        photos_imported=photos_imported,
        skipped=skipped,
    )
    return {
        "folders_created": folders_created,
        "photos_imported": photos_imported,
        "skipped": skipped,
        "errors": errors,
    }


# ── File serving (X-Accel-Redirect) ──────────────────────────────────────────

_THUMB_SIZES = {200, 400, 600, 1000, 1600}


@router.get("/thumbnail/{photo_id}/{size}")
async def get_thumbnail(
    photo_id: uuid.UUID, size: int, db: DbDep, user: CurrentUser, redis: RedisDep,
    format: str = Query(default="webp", pattern="^(webp|avif)$"),
) -> Response:
    if size not in _THUMB_SIZES:
        raise HTTPException(status_code=400, detail="Invalid thumbnail size")
    res = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, "viewer", db, redis)

    thumb_fs = photos_storage.thumb_path(photo_id, size)
    if not thumb_fs.exists():
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder:
            original_path = photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
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

    if format == "avif":
        avif_fs = photos_storage.thumb_avif_path(photo_id, size)
        if avif_fs.exists():
            return Response(
                status_code=200,
                headers={
                    "X-Accel-Redirect": f"/internal/photos-thumbs/{photo_id}/{size}.avif",
                    "Content-Type": "image/avif",
                    "Cache-Control": "public, max-age=3600",
                },
            )

    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/internal/photos-thumbs/{photo_id}/{size}.webp",
            "Content-Type": "image/webp",
            "Cache-Control": "public, max-age=3600",
        },
    )


def _content_disposition(photo: Photo, *, download: bool) -> str:
    from urllib.parse import quote as _q
    disp = "attachment" if download else "inline"
    safe_ascii = re.sub(r"[^A-Za-z0-9._-]", "_", photo.original_name or photo.filename)
    encoded = _q(photo.original_name or photo.filename, safe="")
    return f"{disp}; filename=\"{safe_ascii}\"; filename*=UTF-8''{encoded}"


def _serve_original_response(photo: Photo, folder: PhotoFolder, *, download: bool) -> Response:
    from urllib.parse import quote as _q
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", photo.filename)
    fs_path = folder.fs_path or folder.path or ""
    # X-Accel-Redirect требует URL-encoded путь для не-ASCII сегментов
    encoded_path = _q(fs_path, safe="/")
    internal = f"/internal/photos-originals/{encoded_path}/{safe_name}" if encoded_path else f"/internal/photos-originals/{safe_name}"
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": internal,
            "Content-Type": photo.mime_type or "application/octet-stream",
            "Content-Disposition": _content_disposition(photo, download=download),
        },
    )


@router.get("/original/{photo_id}")
async def get_original(
    photo_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep,
    download: bool = Query(default=False),
) -> Response:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, "viewer", db, redis)
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder missing")
    return _serve_original_response(photo, folder, download=download)


# ── Public folder share ───────────────────────────────────────────────────────

@router.get("/public-folder/{token}/info")
async def public_folder_info(token: str, db: DbDep) -> dict:
    tok_row = await db.scalar(select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token))
    if not tok_row:
        raise HTTPException(status_code=404, detail="Not found")
    _resolve_folder_token_sync_check(tok_row)
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == tok_row.folder_id, PhotoFolder.deleted_at.is_(None)))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    count = await db.scalar(select(func.count(Photo.id)).where(Photo.folder_id == folder.id, Photo.deleted_at.is_(None)))
    return {"folder_name": folder.name, "photos_count": int(count or 0), "created_at": tok_row.created_at.isoformat()}


@router.get("/public-folder/{token}/photos", response_model=PhotoList)
async def public_folder_photos(
    token: str, db: DbDep,
    page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200),
) -> PhotoList:
    tok_row = await db.scalar(select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token))
    if not tok_row:
        raise HTTPException(status_code=404, detail="Not found")
    _resolve_folder_token_sync_check(tok_row)
    base = select(Photo).where(Photo.folder_id == tok_row.folder_id, Photo.deleted_at.is_(None), Photo.processed.is_(True))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    res = await db.execute(base.order_by(Photo.created_at.desc()).offset((page - 1) * per_page).limit(per_page))
    return PhotoList(items=[_photo_to_public(p) for p in res.scalars().all()], total=int(total or 0), page=page, per_page=per_page)


@router.get("/public-folder/{token}/thumbnail/{photo_id}/{size}")
async def public_folder_thumbnail(token: str, photo_id: uuid.UUID, size: int, db: DbDep) -> Response:
    if size not in _THUMB_SIZES:
        raise HTTPException(status_code=400, detail="Invalid size")
    tok_row = await db.scalar(select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token))
    if not tok_row:
        raise HTTPException(status_code=404, detail="Not found")
    _resolve_folder_token_sync_check(tok_row)
    photo = await db.scalar(select(Photo).where(Photo.id == photo_id, Photo.folder_id == tok_row.folder_id, Photo.deleted_at.is_(None)))
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    thumb = photos_storage.thumb_path(photo.id, size)
    if not thumb.exists():
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder:
            orig = photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
            if orig.exists():
                try:
                    photos_storage.generate_thumbnails(photo.id, orig)
                except Exception:
                    pass
    if not thumb.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/internal/photos-thumbs/{photo.id}/{size}.webp",
            "Cache-Control": "public, max-age=3600",
        },
    )


# ── Public sharing ───────────────────────────────────────────────────────────

import secrets as _secrets  # noqa: E402

from app.models.photos import PhotoShareToken  # noqa: E402
from app.schemas.photos import ShareLinkPublic, ShareLinkRequest  # noqa: E402


def _ensure_thumb(photo_id: uuid.UUID, folder: PhotoFolder, photo: Photo, size: int) -> bool:
    p = photos_storage.thumb_path(photo_id, size)
    if p.exists():
        return True
    original_path = photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
    if not original_path.exists():
        return False
    try:
        photos_storage.generate_thumbnails(photo_id, original_path)
        return True
    except Exception:
        return False


@router.post("/{photo_id}/share", response_model=ShareLinkPublic, status_code=201)
async def create_share_link(
    photo_id: uuid.UUID, request: Request, body: ShareLinkRequest,
    db: DbDep, user: CurrentUser, redis: RedisDep,
) -> ShareLinkPublic:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, "uploader", db, redis)

    token = _secrets.token_urlsafe(32)
    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(UTC).replace(microsecond=0) + timedelta(days=body.expires_in_days)

    link = PhotoShareToken(
        photo_id=photo_id, token=token, created_by=user.id, expires_at=expires_at,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    sys_cfg = load_system_settings()
    base = sys_cfg.portal_base_url or _get_settings().portal_base_url or str(request.base_url).rstrip("/")
    public_url = f"{base}/p/{token}"

    await push_audit_event(
        redis, event_type="photos.share_created", user_id=str(user.id), user_email=user.email,
        resource_type="photo", resource_id=str(photo_id),
        metadata={"token_id": str(link.id), "expires_at": expires_at.isoformat() if expires_at else None},
    )

    return ShareLinkPublic(
        id=link.id, photo_id=link.photo_id, token=link.token, url=public_url,
        created_at=link.created_at, expires_at=link.expires_at,
    )


async def _resolve_token(db: AsyncSession, token: str) -> tuple[Photo, PhotoFolder]:
    res = await db.execute(select(PhotoShareToken).where(PhotoShareToken.token == token))
    link = res.scalar_one_or_none()
    if not link or link.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Link not found")
    if link.expires_at is not None and link.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Link expired")
    res2 = await db.execute(select(Photo).where(Photo.id == link.photo_id, Photo.deleted_at.is_(None)))
    photo = res2.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder missing")
    return photo, folder


@router.get("/public/{token}/info", response_model=PhotoPublic)
async def public_photo_info(token: str, db: DbDep) -> PhotoPublic:
    photo, folder = await _resolve_token(db, token)
    return PhotoPublic(
        id=photo.id, folder_id=photo.folder_id, folder_path=folder.path,
        filename=photo.filename, original_name=photo.original_name,
        size_bytes=photo.size_bytes, mime_type=photo.mime_type,
        width=photo.width, height=photo.height, taken_at=photo.taken_at,
        description=photo.description, processed=photo.processed,
        uploaded_by=None, created_at=photo.created_at,
    )


@router.get("/public/{token}/thumbnail/{size}")
async def public_thumbnail(
    token: str, size: int, db: DbDep,
    format: str = Query(default="webp", pattern="^(webp|avif)$"),
) -> Response:
    if size not in _THUMB_SIZES:
        raise HTTPException(status_code=400, detail="Invalid thumbnail size")
    photo, folder = await _resolve_token(db, token)
    if not _ensure_thumb(photo.id, folder, photo, size):
        raise HTTPException(status_code=500, detail="Thumbnail generation failed")
    if format == "avif":
        avif_fs = photos_storage.thumb_avif_path(photo.id, size)
        if avif_fs.exists():
            return Response(
                status_code=200,
                headers={
                    "X-Accel-Redirect": f"/internal/photos-thumbs/{photo.id}/{size}.avif",
                    "Content-Type": "image/avif",
                    "Cache-Control": "public, max-age=3600",
                },
            )
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/internal/photos-thumbs/{photo.id}/{size}.webp",
            "Content-Type": "image/webp",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/public/{token}/file")
async def public_original(
    token: str, db: DbDep,
    download: bool = Query(default=False),
) -> Response:
    photo, folder = await _resolve_token(db, token)
    return _serve_original_response(photo, folder, download=download)
