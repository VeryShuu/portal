"""KB permissions endpoints (sections, articles, inherit, user search)."""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.kb import permissions_repo
from app.core.logging import get_logger
from app.schemas.kb_extra import (
    InheritRequest,
    PermissionEntry,
    PermissionList,
    SetPermissionRequest,
    UserSearchResult,
)
from app.services import keycloak as kc_service
from app.services.acl_base import SYSTEM_ALL_USERS_NAME, SYSTEM_ALL_USERS_SUBJECT_ID
from app.services.audit import make_audit_emitter
from app.services.kb_acl import (
    invalidate_article_cache,
    invalidate_section_cache,
    require_article_permission,
    require_section_permission,
)

from ._common import _get_article_or_404

router = APIRouter(prefix="/kb", tags=["knowledge-base"])
logger = get_logger(__name__)

_emit_section = make_audit_emitter("kb_section")
_emit_article = make_audit_emitter("kb_article")


async def _build_creator_entry(
    db: DbDep,
    created_by: uuid.UUID | None,
) -> PermissionEntry | None:
    if not created_by:
        return None
    creator = await permissions_repo.get_user(db, created_by)
    if not creator:
        return None
    return PermissionEntry(
        id=None,
        subject_type="user",
        subject_id=str(creator.id),
        subject_name=creator.full_name,
        email=creator.email,
        permission="manager",
        is_creator=True,
    )


def _merge_creator(
    entries: list[PermissionEntry],
    creator: PermissionEntry | None,
) -> list[PermissionEntry]:
    if creator is None:
        return entries
    filtered = [
        e for e in entries if not (e.subject_type == "user" and e.subject_id == creator.subject_id)
    ]
    return [creator, *filtered]


@router.get("/sections/{section_id}/permissions", response_model=PermissionList)
async def get_section_permissions(
    section_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionList:
    section = await permissions_repo.get_section(db, section_id)
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)
    items = await permissions_repo.list_section_permissions(db, section_id)
    entries = [PermissionEntry.model_validate(i) for i in items]
    creator = await _build_creator_entry(db, section.created_by)
    return PermissionList(items=_merge_creator(entries, creator))


@router.post("/sections/{section_id}/permissions", response_model=PermissionEntry, status_code=201)
async def set_section_permission(
    section_id: uuid.UUID,
    body: SetPermissionRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionEntry:
    section = await permissions_repo.get_section(db, section_id)
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)
    if (
        section.created_by
        and body.subject_type == "user"
        and body.subject_id == str(section.created_by)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify creator's permission",
        )

    perm = await permissions_repo.upsert_section_permission(
        db,
        section_id=section_id,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        subject_name=body.subject_name,
        permission=body.permission,
        granted_by=user.id,
    )
    await db.commit()
    await invalidate_section_cache(redis, section_id, db)
    await _emit_section(
        redis,
        event_type="kb.permission_grant",
        user_id=str(user.id),
        resource_id=str(section_id),
        metadata={
            "subject_id": body.subject_id,
            "subject_type": body.subject_type,
            "permission": body.permission,
        },
    )
    return cast(PermissionEntry, PermissionEntry.model_validate(perm))


@router.delete("/sections/{section_id}/permissions/{subject_id}", status_code=204)
async def delete_section_permission(
    section_id: uuid.UUID,
    subject_id: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> None:
    section = await permissions_repo.get_section(db, section_id)
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)
    if section.created_by and subject_id == str(section.created_by):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot revoke creator's permission",
        )
    await permissions_repo.delete_section_permission(
        db, section_id=section_id, subject_id=subject_id
    )
    await db.commit()
    await invalidate_section_cache(redis, section_id, db)
    await _emit_section(
        redis,
        event_type="kb.permission_revoke",
        user_id=str(user.id),
        resource_id=str(section_id),
        metadata={"subject_id": subject_id},
    )


@router.get("/articles/{article_id}/permissions", response_model=PermissionList)
async def get_article_permissions(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionList:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "manager", db, redis)
    items = await permissions_repo.list_article_permissions(db, article_id)
    entries = [PermissionEntry.model_validate(i) for i in items]
    creator = await _build_creator_entry(db, article.created_by)
    return PermissionList(items=_merge_creator(entries, creator))


@router.post("/articles/{article_id}/permissions", response_model=PermissionEntry, status_code=201)
async def set_article_permission(
    article_id: uuid.UUID,
    body: SetPermissionRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionEntry:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "manager", db, redis)
    if (
        article.created_by
        and body.subject_type == "user"
        and body.subject_id == str(article.created_by)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify creator's permission",
        )

    perm = await permissions_repo.upsert_article_permission(
        db,
        article_id=article_id,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        subject_name=body.subject_name,
        permission=body.permission,
        granted_by=user.id,
    )
    await db.commit()
    await invalidate_article_cache(redis, article_id)
    await _emit_article(
        redis,
        event_type="kb.permission_grant",
        user_id=str(user.id),
        resource_id=str(article_id),
        metadata={
            "subject_id": body.subject_id,
            "subject_type": body.subject_type,
            "permission": body.permission,
        },
    )
    return cast(PermissionEntry, PermissionEntry.model_validate(perm))


@router.delete("/articles/{article_id}/permissions/{subject_id}", status_code=204)
async def delete_article_permission(
    article_id: uuid.UUID,
    subject_id: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> None:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "manager", db, redis)
    if article.created_by and subject_id == str(article.created_by):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot revoke creator's permission",
        )
    await permissions_repo.delete_article_permission(
        db, article_id=article_id, subject_id=subject_id
    )
    await db.commit()
    await invalidate_article_cache(redis, article_id)
    await _emit_article(
        redis,
        event_type="kb.permission_revoke",
        user_id=str(user.id),
        resource_id=str(article_id),
        metadata={"subject_id": subject_id},
    )


@router.patch("/sections/{section_id}/inherit", response_model=dict)
async def set_section_inherit_permissions(
    section_id: uuid.UUID,
    body: InheritRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> dict:
    section = await permissions_repo.get_section(db, section_id)
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)

    if not body.inherit_permissions and section.inherit_permissions and section.parent_id:
        parent_perms = await permissions_repo.list_section_permissions(db, section.parent_id)
        for pp in parent_perms:
            await permissions_repo.copy_section_permission(
                db,
                section_id=section_id,
                subject_type=pp.subject_type,
                subject_id=pp.subject_id,
                subject_name=pp.subject_name,
                permission=pp.permission,
                granted_by=user.id,
            )

    section.inherit_permissions = body.inherit_permissions
    await db.commit()

    descendant_ids = await permissions_repo.list_descendant_section_ids(db, section_id)
    for desc_id in descendant_ids:
        await invalidate_section_cache(redis, desc_id, db)
    return {"inherit_permissions": body.inherit_permissions}


@router.patch("/articles/{article_id}/inherit", response_model=dict)
async def set_inherit_permissions(
    article_id: uuid.UUID,
    body: InheritRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> dict:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "manager", db, redis)

    if not body.inherit_permissions and article.inherit_permissions and article.section_id:
        sec_perms = await permissions_repo.list_section_permissions(db, article.section_id)
        for sp in sec_perms:
            await permissions_repo.copy_article_permission(
                db,
                article_id=article_id,
                subject_type=sp.subject_type,
                subject_id=sp.subject_id,
                subject_name=sp.subject_name,
                permission=sp.permission,
                granted_by=user.id,
            )

    article.inherit_permissions = body.inherit_permissions
    await db.commit()
    await invalidate_article_cache(redis, article_id)
    return {"inherit_permissions": body.inherit_permissions}


@router.get("/users/search", response_model=list[UserSearchResult])
async def search_kb_users(
    user: CurrentUser,
    redis: RedisDep,
    q: str = Query(min_length=1, max_length=100),
) -> list[UserSearchResult]:
    try:
        kc_users = await kc_service.search_users(q)
        kc_groups = await kc_service.search_groups(q)
    except Exception as e:
        logger.error("keycloak.search_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Keycloak search failed",
        ) from e

    results: list[UserSearchResult] = []
    q_lower = q.lower().strip()
    if q_lower and (
        q_lower in SYSTEM_ALL_USERS_NAME.lower()
        or SYSTEM_ALL_USERS_NAME.lower().startswith(q_lower)
        or "all" in q_lower
        or "все" in q_lower
    ):
        results.append(
            UserSearchResult(
                subject_type="group",
                subject_id=SYSTEM_ALL_USERS_SUBJECT_ID,
                subject_name=SYSTEM_ALL_USERS_NAME,
            )
        )
    for u in kc_users[:10]:
        results.append(
            UserSearchResult(
                subject_type="user",
                subject_id=u.get("id", ""),
                subject_name=u.get("firstName", "") + " " + u.get("lastName", ""),
                email=u.get("email"),
            )
        )
    for g in kc_groups[:10]:
        results.append(
            UserSearchResult(
                subject_type="group",
                subject_id=g.get("path", g.get("name", "")),
                subject_name=g.get("name", ""),
            )
        )
    return results
