"""KB permissions endpoints (sections, articles, inherit, user search)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.logging import get_logger
from app.models.kb import KbArticlePermission, KbSection, KbSectionPermission
from app.schemas.kb_extra import (
    InheritRequest,
    PermissionEntry,
    PermissionList,
    SetPermissionRequest,
    UserSearchResult,
)
from app.services import keycloak as kc_service
from app.services.acl_base import SYSTEM_ALL_USERS_NAME, SYSTEM_ALL_USERS_SUBJECT_ID
from app.services.audit import push_audit_event
from app.services.kb_acl import (
    invalidate_article_cache,
    invalidate_section_cache,
    require_article_permission,
    require_section_permission,
)

from ._common import _get_article_or_404

router = APIRouter(prefix="/kb", tags=["knowledge-base"])
logger = get_logger(__name__)


@router.get("/sections/{section_id}/permissions", response_model=PermissionList)
async def get_section_permissions(
    section_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionList:
    sec_res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    section = sec_res.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)
    result = await db.execute(
        select(KbSectionPermission).where(KbSectionPermission.section_id == section_id)
    )
    items = result.scalars().all()
    return PermissionList(items=[PermissionEntry.model_validate(i) for i in items])


@router.post("/sections/{section_id}/permissions", response_model=PermissionEntry, status_code=201)
async def set_section_permission(
    section_id: uuid.UUID,
    body: SetPermissionRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionEntry:
    sec_res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    section = sec_res.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)

    stmt = (
        pg_insert(KbSectionPermission)
        .values(
            section_id=section_id,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            subject_name=body.subject_name,
            permission=body.permission,
            granted_by=user.id,
        )
        .on_conflict_do_update(
            constraint="uq_kb_sec_perm_section_subject",
            set_={
                "permission": body.permission,
                "subject_name": body.subject_name,
                "granted_by": user.id,
            },
        )
        .returning(KbSectionPermission)
    )
    result = await db.execute(stmt)
    perm = result.scalar_one()
    await db.commit()
    await invalidate_section_cache(redis, section_id, db)
    await push_audit_event(
        redis,
        event_type="kb.permission_grant",
        user_id=str(user.id),
        resource_type="kb_section",
        resource_id=str(section_id),
        metadata={
            "subject_id": body.subject_id,
            "subject_type": body.subject_type,
            "permission": body.permission,
        },
    )
    return PermissionEntry.model_validate(perm)


@router.delete("/sections/{section_id}/permissions/{subject_id}", status_code=204)
async def delete_section_permission(
    section_id: uuid.UUID,
    subject_id: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> None:
    sec_res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    section = sec_res.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)
    await db.execute(
        delete(KbSectionPermission).where(
            KbSectionPermission.section_id == section_id,
            KbSectionPermission.subject_id == subject_id,
        )
    )
    await db.commit()
    await invalidate_section_cache(redis, section_id, db)
    await push_audit_event(
        redis,
        event_type="kb.permission_revoke",
        user_id=str(user.id),
        resource_type="kb_section",
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
    result = await db.execute(
        select(KbArticlePermission).where(KbArticlePermission.article_id == article_id)
    )
    items = result.scalars().all()
    return PermissionList(items=[PermissionEntry.model_validate(i) for i in items])


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

    stmt = (
        pg_insert(KbArticlePermission)
        .values(
            article_id=article_id,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            subject_name=body.subject_name,
            permission=body.permission,
            granted_by=user.id,
        )
        .on_conflict_do_update(
            constraint="uq_kb_art_perm_article_subject",
            set_={
                "permission": body.permission,
                "subject_name": body.subject_name,
                "granted_by": user.id,
            },
        )
        .returning(KbArticlePermission)
    )
    result = await db.execute(stmt)
    perm = result.scalar_one()
    await db.commit()
    await invalidate_article_cache(redis, article_id)
    await push_audit_event(
        redis,
        event_type="kb.permission_grant",
        user_id=str(user.id),
        resource_type="kb_article",
        resource_id=str(article_id),
        metadata={
            "subject_id": body.subject_id,
            "subject_type": body.subject_type,
            "permission": body.permission,
        },
    )
    return PermissionEntry.model_validate(perm)


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
    await db.execute(
        delete(KbArticlePermission).where(
            KbArticlePermission.article_id == article_id,
            KbArticlePermission.subject_id == subject_id,
        )
    )
    await db.commit()
    await invalidate_article_cache(redis, article_id)
    await push_audit_event(
        redis,
        event_type="kb.permission_revoke",
        user_id=str(user.id),
        resource_type="kb_article",
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
    sec_res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    section = sec_res.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)

    if not body.inherit_permissions and section.inherit_permissions and section.parent_id:
        parent_perms_res = await db.execute(
            select(KbSectionPermission).where(
                KbSectionPermission.section_id == section.parent_id
            )
        )
        parent_perms = parent_perms_res.scalars().all()
        for pp in parent_perms:
            stmt = (
                pg_insert(KbSectionPermission)
                .values(
                    section_id=section_id,
                    subject_type=pp.subject_type,
                    subject_id=pp.subject_id,
                    subject_name=pp.subject_name,
                    permission=pp.permission,
                    granted_by=user.id,
                )
                .on_conflict_do_nothing()
            )
            await db.execute(stmt)

    section.inherit_permissions = body.inherit_permissions
    await db.commit()

    descendants_result = await db.execute(
        text("""
            WITH RECURSIVE descendants AS (
                SELECT id FROM kb_sections
                WHERE id = :section_id AND deleted_at IS NULL
                UNION ALL
                SELECT s.id FROM kb_sections s
                JOIN descendants d ON s.parent_id = d.id
                WHERE s.deleted_at IS NULL
            )
            SELECT id FROM descendants
        """),
        {"section_id": str(section_id)},
    )
    for (desc_id,) in descendants_result.fetchall():
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
        sec_perms_res = await db.execute(
            select(KbSectionPermission).where(KbSectionPermission.section_id == article.section_id)
        )
        sec_perms = sec_perms_res.scalars().all()
        for sp in sec_perms:
            stmt = (
                pg_insert(KbArticlePermission)
                .values(
                    article_id=article_id,
                    subject_type=sp.subject_type,
                    subject_id=sp.subject_id,
                    subject_name=sp.subject_name,
                    permission=sp.permission,
                    granted_by=user.id,
                )
                .on_conflict_do_nothing()
            )
            await db.execute(stmt)

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
