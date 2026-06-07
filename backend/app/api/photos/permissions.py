"""ACL grant/revoke for photo folders."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_MANAGER
from app.core.logging import get_logger
from app.models.photos import PhotoFolderPermission
from app.schemas.photos import (
    GrantPermissionRequest,
    PermissionList,
    PermissionPublic,
)
from app.services import keycloak as kc_service
from app.services import photos_permission_repo, photos_photo_repo
from app.services.acl_base import SYSTEM_ALL_USERS_NAME, SYSTEM_ALL_USERS_SUBJECT_ID
from app.services.audit import make_audit_emitter
from app.services.photos_acl import invalidate_folder_cache, require_folder_permission

logger = get_logger(__name__)

router = APIRouter()

_emit_audit = make_audit_emitter("photo_folder")


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
    folder = await photos_photo_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    perms = await photos_permission_repo.list_folder_permissions(db, folder_id)
    items = [PermissionPublic.model_validate(p) for p in perms]
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
    folder = await photos_photo_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)

    perm = await photos_permission_repo.find_folder_permission(
        db,
        folder_id=folder_id,
        subject_type=data.subject_type,
        subject_id=data.subject_id,
    )
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
        perm = await photos_permission_repo.find_folder_permission(
            db,
            folder_id=folder_id,
            subject_type=data.subject_type,
            subject_id=data.subject_id,
        )
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
    await _emit_audit(
        redis,
        event_type="photos.permission_granted",
        user_id=str(user.id),
        user_email=user.email,
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
    folder = await photos_photo_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)

    await photos_permission_repo.delete_folder_permission(
        db, folder_id=folder_id, subject_id=subject_id, subject_type=subject_type
    )
    await db.commit()
    await invalidate_folder_cache(redis, folder_id, db)
    await _emit_audit(
        redis,
        event_type="photos.permission_revoked",
        user_id=str(user.id),
        user_email=user.email,
        resource_id=str(folder_id),
        metadata={"subject_id": subject_id},
    )
    return Response(status_code=204)
