"""KB sections endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.kb import sections_repo
from app.models.kb import KbSection
from app.schemas.kb import (
    CreateSectionRequest,
    KbSectionList,
    KbSectionPublic,
    UpdateSectionRequest,
)
from app.services.audit import make_audit_emitter
from app.services.kb_acl import (
    batch_resolve_section_permissions,
    invalidate_section_cache,
    require_section_permission,
    resolve_section_permission,
)

from ._common import _slugify

_emit_audit = make_audit_emitter("kb_section")

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("/sections", response_model=KbSectionList, summary="Дерево разделов")
async def get_sections(db: DbDep, user: CurrentUser, redis: RedisDep) -> KbSectionList:
    sections = list(await sections_repo.list_active_sections(db))

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
        parent_section = await sections_repo.get_active_section(db, body.parent_id)
        if not parent_section:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Parent section not found"
            )
        await require_section_permission(user, parent_section, "editor", db, redis)

    slug = _slugify(body.title)
    if await sections_repo.find_section_by_slug(db, slug=slug, parent_id=body.parent_id):
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
    section = await sections_repo.get_active_section(db, section_id)
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
            parent_sec = await sections_repo.get_active_section(db, body.parent_id)
            if not parent_sec:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Parent section not found"
                )
            await require_section_permission(user, parent_sec, "editor", db, redis)
            if await sections_repo.is_descendant(
                db, section_id=section_id, parent_id=body.parent_id
            ):
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
    section = await sections_repo.get_active_section(db, section_id)
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")

    await require_section_permission(user, section, "manager", db, redis)

    if await sections_repo.has_active_children(db, section_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Раздел содержит дочерние разделы. Сначала удалите их.",
        )

    if await sections_repo.has_active_articles(db, section_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Раздел содержит статьи. Перенесите или удалите статьи перед удалением раздела.",
        )

    now = datetime.now(UTC)
    section.deleted_at = now
    await sections_repo.detach_trashed_articles(db, section_id)
    await db.commit()
    await _emit_audit(
        redis,
        event_type="kb.section_deleted",
        user_id=str(user.id),
        user_email=user.email,
        resource_id=str(section_id),
    )
