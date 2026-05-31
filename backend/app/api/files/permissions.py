"""Folder permissions CRUD + subject search."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.models.files import FileFolder, FileFolderPermission
from app.models.user import User
from app.schemas.files import (
    FileFolderPublic,
    GrantPermissionRequest,
    PermissionList,
    PermissionPublic,
)
from app.services import keycloak as kc_service
from app.services.acl_base import SYSTEM_ALL_USERS_NAME, SYSTEM_ALL_USERS_SUBJECT_ID
from app.services.audit import push_audit_event
from app.services.files_acl import (
    invalidate_folder_cache,
    require_folder_permission,
    resolve_folder_permission,
)
from app.services.files_acl_persistence import AclEntry, save_folder_perms

from ._common import ModuleCheck, _folder_to_public, _get_folder_or_404, logger

router = APIRouter(tags=["files"])


# ── Subject search ─────────────────────────────────────────────────────────────


class SubjectSearchResult(BaseModel):
    subject_type: str
    subject_id: str
    subject_name: str
    email: str | None = None


@router.get(
    "/files/users/search",
    response_model=list[SubjectSearchResult],
    dependencies=[ModuleCheck],
)
async def search_files_subjects(
    q: str = Query(min_length=1, max_length=100),
    user: CurrentUser = ...,  # type: ignore[assignment]
) -> list[SubjectSearchResult]:
    if user.role not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        kc_users = await kc_service.search_users(q)
        kc_groups = await kc_service.search_groups(q)
    except Exception as e:
        logger.warning("keycloak.search_failed", error=str(e))
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


# ── Creator entry helpers (parity with KB) ──────────────────────────────────────


async def _build_creator_entry(
    db: DbDep,
    folder: FileFolder,
) -> PermissionPublic | None:
    if not folder.created_by:
        return None
    res = await db.execute(select(User).where(User.id == folder.created_by))
    creator = res.scalar_one_or_none()
    if not creator:
        return None
    return PermissionPublic(
        id=None,
        folder_id=folder.id,
        subject_type="user",
        subject_id=str(creator.id),
        subject_name=creator.full_name,
        email=creator.email,
        permission="manager",
        is_creator=True,
    )


def _merge_creator(
    entries: list[PermissionPublic],
    creator: PermissionPublic | None,
) -> list[PermissionPublic]:
    if creator is None:
        return entries
    filtered = [
        e for e in entries if not (e.subject_type == "user" and e.subject_id == creator.subject_id)
    ]
    return [creator, *filtered]


def _is_creator_subject(folder: FileFolder, subject_type: str, subject_id: str) -> bool:
    return bool(
        folder.created_by
        and subject_type == "user"
        and subject_id == str(folder.created_by)
    )


# ── List permissions ───────────────────────────────────────────────────────────


@router.get(
    "/files/folders/{folder_id}/permissions",
    response_model=PermissionList,
    dependencies=[ModuleCheck],
)
async def list_permissions(
    folder_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> PermissionList:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)
    res = await db.execute(
        select(FileFolderPermission).where(FileFolderPermission.folder_id == folder_id)
    )
    perms = res.scalars().all()
    entries = [PermissionPublic.model_validate(p) for p in perms]
    creator = await _build_creator_entry(db, folder)
    return PermissionList(items=_merge_creator(entries, creator))


# ── Grant permission ───────────────────────────────────────────────────────────


@router.post(
    "/files/folders/{folder_id}/permissions",
    response_model=PermissionPublic,
    status_code=201,
    dependencies=[ModuleCheck],
)
async def grant_permission(
    folder_id: uuid.UUID,
    body: GrantPermissionRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> PermissionPublic:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    if _is_creator_subject(folder, body.subject_type, body.subject_id):
        raise HTTPException(status_code=409, detail="Cannot modify creator's permission")

    existing = await db.execute(
        select(FileFolderPermission).where(
            FileFolderPermission.folder_id == folder_id,
            FileFolderPermission.subject_id == body.subject_id,
        )
    )
    perm_row = existing.scalar_one_or_none()
    if perm_row:
        perm_row.permission = body.permission
        perm_row.subject_name = body.subject_name
        perm_row.granted_by = user.id
    else:
        perm_row = FileFolderPermission(
            folder_id=folder_id,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            subject_name=body.subject_name,
            permission=body.permission,
            granted_by=user.id,
            created_at=datetime.now(UTC),
        )
        db.add(perm_row)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        res2 = await db.execute(
            select(FileFolderPermission).where(
                FileFolderPermission.folder_id == folder_id,
                FileFolderPermission.subject_id == body.subject_id,
            )
        )
        perm_row = res2.scalar_one_or_none()
        if perm_row is None:
            raise HTTPException(
                status_code=409,
                detail="Permission conflict, please retry",
            ) from exc
        perm_row.permission = body.permission
        perm_row.subject_name = body.subject_name
        perm_row.granted_by = user.id
        await db.commit()
    await db.refresh(perm_row)
    await invalidate_folder_cache(redis, folder_id, db)
    await push_audit_event(
        redis,
        event_type="files.permission_granted",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="folder",
        resource_id=str(folder_id),
        metadata={"subject_id": body.subject_id, "permission": body.permission},
    )
    all_perms = await db.execute(
        select(FileFolderPermission).where(FileFolderPermission.folder_id == folder_id)
    )
    await save_folder_perms(
        folder.nc_path,
        [
            AclEntry(
                subject_type=p.subject_type,
                subject_id=p.subject_id,
                subject_name=p.subject_name,
                permission=p.permission,
            )
            for p in all_perms.scalars().all()
        ],
    )
    return PermissionPublic.model_validate(perm_row)


# ── Revoke permission ──────────────────────────────────────────────────────────


@router.delete(
    "/files/folders/{folder_id}/permissions/{perm_id}",
    status_code=204,
    dependencies=[ModuleCheck],
)
async def revoke_permission(
    folder_id: uuid.UUID,
    perm_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> None:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    res = await db.execute(
        select(FileFolderPermission).where(
            FileFolderPermission.id == perm_id,
            FileFolderPermission.folder_id == folder_id,
        )
    )
    perm_row = res.scalar_one_or_none()
    if not perm_row:
        raise HTTPException(status_code=404, detail="Permission not found")

    if _is_creator_subject(folder, perm_row.subject_type, perm_row.subject_id):
        raise HTTPException(status_code=409, detail="Cannot revoke creator's permission")

    subject_id = perm_row.subject_id
    await db.delete(perm_row)
    await db.commit()
    await invalidate_folder_cache(redis, folder_id, db)
    await push_audit_event(
        redis,
        event_type="files.permission_revoked",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="folder",
        resource_id=str(folder_id),
        metadata={"perm_id": str(perm_id), "subject_id": subject_id},
    )
    remaining = await db.execute(
        select(FileFolderPermission).where(FileFolderPermission.folder_id == folder_id)
    )
    await save_folder_perms(
        folder.nc_path,
        [
            AclEntry(
                subject_type=p.subject_type,
                subject_id=p.subject_id,
                subject_name=p.subject_name,
                permission=p.permission,
            )
            for p in remaining.scalars().all()
        ],
    )


# ── Inheritance toggle ─────────────────────────────────────────────────────────


class SetInheritanceRequest(BaseModel):
    inherit_permissions: bool


@router.patch(
    "/files/folders/{folder_id}/inheritance",
    response_model=FileFolderPublic,
    dependencies=[ModuleCheck],
)
async def set_folder_inheritance(
    folder_id: uuid.UUID,
    body: SetInheritanceRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> FileFolderPublic:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    if folder.inherit_permissions != body.inherit_permissions:
        folder.inherit_permissions = body.inherit_permissions
        await db.commit()
        await db.refresh(folder)
        await invalidate_folder_cache(redis, folder_id, db)
        await push_audit_event(
            redis,
            event_type="files.folder_inheritance_changed",
            user_id=str(user.id),
            user_email=user.email,
            resource_type="folder",
            resource_id=str(folder_id),
            metadata={"inherit_permissions": body.inherit_permissions},
        )

    perm = await resolve_folder_permission(user, folder, db, redis)
    return await _folder_to_public(folder, perm)
