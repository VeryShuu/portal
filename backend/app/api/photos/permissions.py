"""ACL grant/revoke for photo folders."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_MANAGER
from app.core.logging import get_logger
from app.models.photos import PhotoFolder, PhotoFolderPermission
from app.schemas.photos import (
    GrantPermissionRequest,
    PermissionList,
    PermissionPublic,
)
from app.services import keycloak as kc_service
from app.services.acl_base import SYSTEM_ALL_USERS_NAME, SYSTEM_ALL_USERS_SUBJECT_ID
from app.services.audit import push_audit_event
from app.services.photos_acl import invalidate_folder_cache, require_folder_permission

logger = get_logger(__name__)

router = APIRouter()


class SubjectSearchResult(BaseModel):
    subject_type: str
    subject_id: str
    subject_name: str
    email: str | None = None


@router.get("/users/search", response_model=list[SubjectSearchResult])
async def search_photo_subjects(
    user: CurrentUser,
    q: str = Query(min_length=1, max_length=100),
) -> list[SubjectSearchResult]:
    if user.role not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        kc_users = await kc_service.search_users(q)
        kc_groups = await kc_service.search_groups(q)
    except Exception as e:
        logger.warning("photos.keycloak.search_failed", error=str(e))
        kc_users, kc_groups = [], []

    results: list[SubjectSearchResult] = []
    q_lower = q.lower().strip()
    if q_lower and (
        q_lower in SYSTEM_ALL_USERS_NAME.lower()
        or SYSTEM_ALL_USERS_NAME.lower().startswith(q_lower)
        or "all" in q_lower
        or "все" in q_lower
    ):
        results.append(
            SubjectSearchResult(
                subject_type="group",
                subject_id=SYSTEM_ALL_USERS_SUBJECT_ID,
                subject_name=SYSTEM_ALL_USERS_NAME,
            )
        )
    for u in kc_users[:10]:
        results.append(
            SubjectSearchResult(
                subject_type="user",
                subject_id=u.get("id", ""),
                subject_name=(u.get("firstName", "") + " " + u.get("lastName", "")).strip(),
                email=u.get("email"),
            )
        )
    for g in kc_groups[:10]:
        results.append(
            SubjectSearchResult(
                subject_type="group",
                subject_id=g.get("path", g.get("name", "")),
                subject_name=g.get("name", ""),
            )
        )
    return results


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
            PhotoFolderPermission.subject_type == data.subject_type,
            PhotoFolderPermission.subject_id == data.subject_id,
        )
    )
    perm = existing_res.scalar_one_or_none()
    previous_permission: str | None = perm.permission if perm else None

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
                PhotoFolderPermission.subject_type == data.subject_type,
                PhotoFolderPermission.subject_id == data.subject_id,
            )
        )
        perm = res2.scalar_one_or_none()
        if perm is None:
            raise HTTPException(
                status_code=409,
                detail="Permission conflict, please retry",
            ) from exc
        previous_permission = perm.permission
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
        metadata={
            "subject_id": data.subject_id,
            "permission": data.permission,
            "previous_permission": previous_permission,
        },
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
    subject_type: str | None = Query(default=None, pattern="^(user|group)$"),
) -> Response:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)

    q = delete(PhotoFolderPermission).where(
        PhotoFolderPermission.folder_id == folder_id,
        PhotoFolderPermission.subject_id == subject_id,
    )
    if subject_type:
        q = q.where(PhotoFolderPermission.subject_type == subject_type)
    await db.execute(q)
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
