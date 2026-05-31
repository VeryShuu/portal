"""Per-file sharing API (sharing.md).

Endpoints to share a single file with users/groups, list/revoke shares,
"my shares" / "shared with me" views and an admin registry. Permission
to manage a file's shares always requires ``manager`` on the containing
folder (re-sharing by recipients is impossible by design).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.models.files import FileFolder, FileShare
from app.models.user import User
from app.schemas.files import (
    AdminFileShare,
    AdminFileShareList,
    CreateFileShareRequest,
    FileShareList,
    FileSharePublic,
    MyFileShare,
    MyFileShareList,
    SharedFile,
    SharedFileList,
)
from app.services.acl_base import subject_ids_for_user
from app.services.audit import push_audit_event
from app.services.files_acl import (
    invalidate_file_share_cache,
    require_folder_permission,
)
from app.services.files_shares_persistence import (
    ShareEntry,
    drop_file_shares,
    save_file_shares,
)
from app.services.nextcloud import NextcloudError, get_nc_service

from ._common import ModuleCheck, _get_folder_or_404, logger, sanitize_name
from ._share_notify import notify_file_shared

router = APIRouter(tags=["files"])


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _share_to_public(s: FileShare) -> FileSharePublic:
    return FileSharePublic(
        id=s.id,
        folder_id=s.folder_id,
        filename=s.filename,
        nc_path=s.nc_path,
        subject_type=s.subject_type,
        subject_id=s.subject_id,
        subject_name=s.subject_name,
        permission=s.permission,
        shared_by=s.shared_by,
        created_at=s.created_at,
        expires_at=s.expires_at,
    )


async def _active_shares_for_file(
    db: DbDep, folder_id: uuid.UUID, filename: str
) -> list[FileShare]:
    res = await db.execute(
        select(FileShare).where(
            FileShare.folder_id == folder_id,
            FileShare.filename == filename,
            FileShare.revoked_at.is_(None),
        )
    )
    return list(res.scalars().all())


async def _persist_file_shares(db: DbDep, folder_id: uuid.UUID, filename: str, nc_path: str) -> None:
    """Mirror active shares for a file into files-shares.json."""
    active = await _active_shares_for_file(db, folder_id, filename)
    if not active:
        await drop_file_shares(nc_path)
        return
    entries: list[ShareEntry] = [
        ShareEntry(
            subject_type=s.subject_type,
            subject_id=s.subject_id,
            subject_name=s.subject_name,
            permission=s.permission,
            expires_at=s.expires_at.isoformat() if s.expires_at else None,
        )
        for s in active
    ]
    await save_file_shares(nc_path, entries)


# ── Create / upsert share ────────────────────────────────────────────────────────


@router.post(
    "/files/folders/{folder_id}/files/{filename}/shares",
    response_model=FileSharePublic,
    status_code=201,
    dependencies=[ModuleCheck, Depends(RateLimiter(times=20, minutes=1))],
)
async def create_file_share(
    folder_id: uuid.UUID,
    filename: str,
    body: CreateFileShareRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> FileSharePublic:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    safe_filename = sanitize_name(filename)
    nc_path = f"{folder.nc_path}/{safe_filename}"

    nc = get_nc_service()
    try:
        exists = await nc.file_exists(nc_path)
    except NextcloudError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    if not exists:
        raise HTTPException(status_code=404, detail="File not found")

    expires_at: datetime | None = None
    if body.expires_in_days:
        expires_at = datetime.now(UTC) + timedelta(days=body.expires_in_days)

    existing = await db.execute(
        select(FileShare).where(
            FileShare.folder_id == folder_id,
            FileShare.filename == safe_filename,
            FileShare.subject_id == body.subject_id,
        )
    )
    share = existing.scalar_one_or_none()
    is_update = share is not None
    if share is not None:
        share.subject_type = body.subject_type
        share.subject_name = body.subject_name
        share.permission = body.permission
        share.nc_path = nc_path
        share.expires_at = expires_at
        share.revoked_at = None
        share.shared_by = user.id
    else:
        share = FileShare(
            folder_id=folder_id,
            filename=safe_filename,
            nc_path=nc_path,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            subject_name=body.subject_name,
            permission=body.permission,
            shared_by=user.id,
            expires_at=expires_at,
            created_at=datetime.now(UTC),
        )
        db.add(share)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Share conflict, please retry") from exc
    await db.refresh(share)

    await invalidate_file_share_cache(redis, folder_id, safe_filename)
    await _persist_file_shares(db, folder_id, safe_filename, nc_path)

    await push_audit_event(
        redis,
        event_type="files.file_share_updated" if is_update else "files.file_shared",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="file",
        resource_title=safe_filename,
        metadata={
            "folder_id": str(folder_id),
            "subject_id": body.subject_id,
            "permission": body.permission,
            "nc_path": nc_path,
        },
    )

    try:
        await notify_file_shared(
            db,
            redis,
            share=share,
            folder=folder,
            shared_by=user,
        )
    except Exception as exc:
        logger.warning("files.share_notify_failed", error=str(exc), share_id=str(share.id))

    return _share_to_public(share)


# ── List shares of a file ─────────────────────────────────────────────────────────


@router.get(
    "/files/folders/{folder_id}/files/{filename}/shares",
    response_model=FileShareList,
    dependencies=[ModuleCheck],
)
async def list_file_shares(
    folder_id: uuid.UUID,
    filename: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> FileShareList:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    safe_filename = sanitize_name(filename)
    shares = await _active_shares_for_file(db, folder_id, safe_filename)
    return FileShareList(items=[_share_to_public(s) for s in shares])


# ── Revoke share ──────────────────────────────────────────────────────────────────


@router.delete(
    "/files/folders/{folder_id}/files/{filename}/shares/{share_id}",
    status_code=204,
    dependencies=[ModuleCheck],
)
async def revoke_file_share(
    folder_id: uuid.UUID,
    filename: str,
    share_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> None:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    safe_filename = sanitize_name(filename)
    res = await db.execute(
        select(FileShare).where(
            FileShare.id == share_id,
            FileShare.folder_id == folder_id,
            FileShare.filename == safe_filename,
        )
    )
    share = res.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    if share.revoked_at is None:
        share.revoked_at = datetime.now(UTC)
        await db.commit()

    await invalidate_file_share_cache(redis, folder_id, safe_filename)
    await _persist_file_shares(db, folder_id, safe_filename, share.nc_path)

    await push_audit_event(
        redis,
        event_type="files.file_share_revoked",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="file",
        resource_title=safe_filename,
        metadata={
            "folder_id": str(folder_id),
            "share_id": str(share_id),
            "subject_id": share.subject_id,
            "nc_path": share.nc_path,
        },
    )


# ── My shares ──────────────────────────────────────────────────────────────────────


@router.get(
    "/files/shares/my",
    response_model=MyFileShareList,
    dependencies=[ModuleCheck],
)
async def list_my_shares(
    user: CurrentUser,
    db: DbDep,
) -> MyFileShareList:
    now = datetime.now(UTC)
    res = await db.execute(
        select(FileShare, FileFolder.name)
        .join(FileFolder, FileShare.folder_id == FileFolder.id)
        .where(
            FileShare.shared_by == user.id,
            FileShare.revoked_at.is_(None),
            (FileShare.expires_at.is_(None)) | (FileShare.expires_at > now),
        )
        .order_by(FileShare.created_at.desc())
    )
    items = [
        MyFileShare(
            id=s.id,
            folder_id=s.folder_id,
            filename=s.filename,
            nc_path=s.nc_path,
            folder_name=folder_name,
            subject_type=s.subject_type,
            subject_id=s.subject_id,
            subject_name=s.subject_name,
            permission=s.permission,
            created_at=s.created_at,
            expires_at=s.expires_at,
        )
        for s, folder_name in res.all()
    ]
    return MyFileShareList(items=items)


# ── Shared with me ──────────────────────────────────────────────────────────────────


@router.get(
    "/files/shares/shared-with-me",
    response_model=SharedFileList,
    dependencies=[ModuleCheck],
)
async def list_shared_with_me(
    user: CurrentUser,
    db: DbDep,
) -> SharedFileList:
    subject_ids = await subject_ids_for_user(user)
    if not subject_ids:
        return SharedFileList(items=[])

    now = datetime.now(UTC)
    res = await db.execute(
        select(FileShare, FileFolder.name, User.full_name)
        .join(FileFolder, FileShare.folder_id == FileFolder.id)
        .outerjoin(User, FileShare.shared_by == User.id)
        .where(
            FileShare.subject_id.in_(subject_ids),
            FileShare.revoked_at.is_(None),
            (FileShare.expires_at.is_(None)) | (FileShare.expires_at > now),
        )
        .order_by(FileShare.created_at.desc())
    )
    items = [
        SharedFile(
            id=s.id,
            folder_id=s.folder_id,
            filename=s.filename,
            nc_path=s.nc_path,
            folder_name=folder_name,
            permission=s.permission,
            shared_by_name=shared_by_name,
            created_at=s.created_at,
            expires_at=s.expires_at,
        )
        for s, folder_name, shared_by_name in res.all()
    ]
    return SharedFileList(items=items)


# ── Admin registry ──────────────────────────────────────────────────────────────────


@router.get(
    "/files/admin/shares",
    response_model=AdminFileShareList,
    dependencies=[ModuleCheck],
)
async def admin_list_shares(
    _admin: AdminDep,
    db: DbDep,
    subject_id: str | None = None,
    folder_id: uuid.UUID | None = None,
    active_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> AdminFileShareList:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    now = datetime.now(UTC)

    conditions = []
    if subject_id:
        conditions.append(FileShare.subject_id == subject_id)
    if folder_id:
        conditions.append(FileShare.folder_id == folder_id)
    if active_only:
        conditions.append(FileShare.revoked_at.is_(None))
        conditions.append((FileShare.expires_at.is_(None)) | (FileShare.expires_at > now))

    count_stmt = select(func.count()).select_from(FileShare)
    for c in conditions:
        count_stmt = count_stmt.where(c)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(FileShare, FileFolder.name, User.full_name)
        .outerjoin(FileFolder, FileShare.folder_id == FileFolder.id)
        .outerjoin(User, FileShare.shared_by == User.id)
    )
    for c in conditions:
        stmt = stmt.where(c)
    stmt = stmt.order_by(FileShare.created_at.desc()).limit(limit).offset(offset)

    res = await db.execute(stmt)
    items = [
        AdminFileShare(
            id=s.id,
            folder_id=s.folder_id,
            filename=s.filename,
            nc_path=s.nc_path,
            folder_name=folder_name,
            subject_type=s.subject_type,
            subject_id=s.subject_id,
            subject_name=s.subject_name,
            permission=s.permission,
            shared_by=s.shared_by,
            shared_by_name=shared_by_name,
            created_at=s.created_at,
            expires_at=s.expires_at,
            revoked_at=s.revoked_at,
        )
        for s, folder_name, shared_by_name in res.all()
    ]
    return AdminFileShareList(items=items, total=total, limit=limit, offset=offset)
