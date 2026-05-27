"""KB sections endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, text, update

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.models.kb import KbArticle, KbSection
from app.schemas.kb import (
    CreateSectionRequest,
    KbSectionList,
    KbSectionPublic,
    UpdateSectionRequest,
)
from app.services.audit import push_audit_event
from app.services.kb_acl import (
    batch_resolve_section_permissions,
    invalidate_section_cache,
    require_section_permission,
    resolve_section_permission,
)

from ._common import _slugify

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("/sections", response_model=KbSectionList, summary="Дерево разделов")
async def get_sections(db: DbDep, user: CurrentUser, redis: RedisDep) -> KbSectionList:
    result = await db.execute(
        select(KbSection)
        .where(KbSection.deleted_at.is_(None))
        .order_by(KbSection.sort_order, KbSection.title)
    )
    sections = list(result.scalars().all())

    perm_map = await batch_resolve_section_permissions(user, sections, db, redis)

    section_map: dict[uuid.UUID, KbSectionPublic] = {}
    for s in sections:
        if perm_map.get(s.id) is None:
            continue
        section_map[s.id] = KbSectionPublic(
            id=s.id,
            parent_id=s.parent_id,
            title=s.title,
            slug=s.slug,
            description=s.description,
            sort_order=s.sort_order,
            inherit_permissions=s.inherit_permissions,
            created_at=s.created_at,
            user_permission=perm_map.get(s.id),
            children=[],
        )

    roots: list[KbSectionPublic] = []
    for s in sections:
        if s.id not in section_map:
            continue
        node = section_map[s.id]
        if s.parent_id and s.parent_id in section_map:
            section_map[s.parent_id].children.append(node)
        else:
            roots.append(node)

    return KbSectionList(items=roots)


@router.post("/sections", status_code=status.HTTP_201_CREATED, summary="Создать раздел")
async def create_section(
    body: CreateSectionRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbSectionPublic:
    if body.parent_id:
        parent_result = await db.execute(
            select(KbSection).where(KbSection.id == body.parent_id, KbSection.deleted_at.is_(None))
        )
        parent_section = parent_result.scalar_one_or_none()
        if not parent_section:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Parent section not found"
            )
        await require_section_permission(user, parent_section, "editor", db, redis)

    slug = _slugify(body.title)
    result = await db.execute(
        select(KbSection).where(
            KbSection.slug == slug,
            KbSection.parent_id == body.parent_id,
        )
    )
    if result.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    section = KbSection(
        title=body.title,
        slug=slug,
        parent_id=body.parent_id,
        description=body.description,
        sort_order=body.sort_order,
        created_by=user.id,
        inherit_permissions=True,
    )
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return KbSectionPublic(
        id=section.id,
        parent_id=section.parent_id,
        title=section.title,
        slug=section.slug,
        description=section.description,
        sort_order=section.sort_order,
        inherit_permissions=section.inherit_permissions,
        created_at=section.created_at,
        user_permission="manager",
        children=[],
    )


@router.put("/sections/{section_id}", summary="Обновить раздел")
async def update_section(
    section_id: uuid.UUID,
    body: UpdateSectionRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbSectionPublic:
    result = await db.execute(
        select(KbSection).where(KbSection.id == section_id, KbSection.deleted_at.is_(None))
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")

    await require_section_permission(user, section, "editor", db, redis)

    parent_changed = False
    old_parent_id = section.parent_id

    if body.title is not None:
        section.title = body.title
    if body.description is not None:
        section.description = body.description
    if body.sort_order is not None:
        section.sort_order = body.sort_order
    if "parent_id" in body.model_fields_set:
        if body.parent_id != old_parent_id:
            parent_changed = True
        if body.parent_id is None:
            section.parent_id = None
        else:
            if body.parent_id == section_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Section cannot be its own parent",
                )
            parent_result = await db.execute(
                select(KbSection).where(
                    KbSection.id == body.parent_id, KbSection.deleted_at.is_(None)
                )
            )
            parent_sec = parent_result.scalar_one_or_none()
            if not parent_sec:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Parent section not found"
                )
            await require_section_permission(user, parent_sec, "editor", db, redis)
            cycle_result = await db.execute(
                text("""
                    WITH RECURSIVE descendants AS (
                        SELECT id FROM kb_sections WHERE id = :section_id AND deleted_at IS NULL
                        UNION ALL
                        SELECT s.id FROM kb_sections s
                        JOIN descendants d ON s.parent_id = d.id
                        WHERE s.deleted_at IS NULL
                    )
                    SELECT 1 FROM descendants WHERE id = :parent_id LIMIT 1
                """),
                {"section_id": str(section_id), "parent_id": str(body.parent_id)},
            )
            if cycle_result.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Cannot set a descendant section as parent — this would create a cycle",
                )
            section.parent_id = body.parent_id

    await db.commit()
    await db.refresh(section)

    if parent_changed:
        # invalidate_section_cache uses a recursive CTE to walk the whole
        # subtree in a single pass and deletes Redis keys via pipeline.
        # No need to iterate per-descendant.
        await invalidate_section_cache(redis, section_id, db)

    user_perm = await resolve_section_permission(user, section, db, redis)
    return KbSectionPublic(
        id=section.id,
        parent_id=section.parent_id,
        title=section.title,
        slug=section.slug,
        description=section.description,
        sort_order=section.sort_order,
        inherit_permissions=section.inherit_permissions,
        created_at=section.created_at,
        user_permission=user_perm,
        children=[],
    )


@router.delete(
    "/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить раздел"
)
async def delete_section(
    section_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> None:
    result = await db.execute(
        select(KbSection).where(KbSection.id == section_id, KbSection.deleted_at.is_(None))
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")

    await require_section_permission(user, section, "manager", db, redis)

    child_result = await db.execute(
        select(KbSection)
        .where(KbSection.parent_id == section_id, KbSection.deleted_at.is_(None))
        .limit(1)
    )
    if child_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Раздел содержит дочерние разделы. Сначала удалите их.",
        )

    active_article_result = await db.execute(
        select(KbArticle)
        .where(KbArticle.section_id == section_id, KbArticle.deleted_at.is_(None))
        .limit(1)
    )
    if active_article_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Раздел содержит статьи. Перенесите или удалите статьи перед удалением раздела.",
        )

    now = datetime.now(UTC)
    section.deleted_at = now
    await db.execute(
        update(KbArticle)
        .where(KbArticle.section_id == section_id, KbArticle.deleted_at.isnot(None))
        .values(section_id=None)
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="kb.section_deleted",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="kb_section",
        resource_id=str(section_id),
    )
