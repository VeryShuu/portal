"""ACL grant/revoke for photo folders."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_MANAGER
from app.models.photos import PhotoFolder, PhotoFolderPermission
from app.schemas.photos import (
    GrantPermissionRequest,
    PermissionList,
    PermissionPublic,
)
from app.services.audit import push_audit_event
from app.services.photos_acl import invalidate_folder_cache, require_folder_permission

router = APIRouter()


@router.get("/folders/{folder_id}/permissions", response_model=PermissionList)
async def list_folder_permissions(
    folder_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> PermissionList:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    res2 = await db.execute(
        select(PhotoFolderPermission)
        .where(PhotoFolderPermission.folder_id == folder_id)
        .order_by(PhotoFolderPermission.created_at)
    )
    items = [PermissionPublic.model_validate(p) for p in res2.scalars().all()]
    return PermissionList(items=items)


@router.post("/folders/{folder_id}/permissions", response_model=PermissionPublic, status_code=201)
async def grant_folder_permission(
    folder_id: uuid.UUID,
    data: GrantPermissionRequest,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionPublic:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)

    existing_res = await db.execute(
        select(PhotoFolderPermission).where(
            PhotoFolderPermission.folder_id == folder_id,
            PhotoFolderPermission.subject_id == data.subject_id,
        )
    )
    perm = existing_res.scalar_one_or_none()

    if perm:
        perm.permission = data.permission
        perm.subject_name = data.subject_name
        perm.subject_type = data.subject_type
        perm.granted_by = user.id
    else:
        perm = PhotoFolderPermission(
            folder_id=folder_id,
            subject_type=data.subject_type,
            subject_id=data.subject_id,
            subject_name=data.subject_name,
            permission=data.permission,
            granted_by=user.id,
        )
        db.add(perm)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        res2 = await db.execute(
            select(PhotoFolderPermission).where(
                PhotoFolderPermission.folder_id == folder_id,
                PhotoFolderPermission.subject_id == data.subject_id,
            )
        )
        perm = res2.scalar_one_or_none()
        if perm is None:
            raise HTTPException(
                status_code=409,
                detail="Permission conflict, please retry",
            ) from exc
        perm.permission = data.permission
        perm.subject_name = data.subject_name
        perm.subject_type = data.subject_type
        perm.granted_by = user.id
        await db.commit()

    await db.refresh(perm)
    await invalidate_folder_cache(redis, folder_id, db)
    await push_audit_event(
        redis,
        event_type="photos.permission_granted",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo_folder",
        resource_id=str(folder_id),
        metadata={"subject_id": data.subject_id, "permission": data.permission},
    )
    return PermissionPublic.model_validate(perm)


@router.delete("/folders/{folder_id}/permissions/{subject_id}", status_code=204)
async def revoke_folder_permission(
    folder_id: uuid.UUID,
    subject_id: str,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    await db.execute(
        delete(PhotoFolderPermission).where(
            PhotoFolderPermission.folder_id == folder_id,
            PhotoFolderPermission.subject_id == subject_id,
        )
    )
    await db.commit()
    await invalidate_folder_cache(redis, folder_id, db)
    await push_audit_event(
        redis,
        event_type="photos.permission_revoked",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo_folder",
        resource_id=str(folder_id),
        metadata={"subject_id": subject_id},
    )
    return Response(status_code=204)
