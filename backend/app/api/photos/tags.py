"""Tag CRUD and per-photo tag management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_EDITOR, PERM_UPLOADER, PERM_VIEWER
from app.models.photos import PhotoTag, PhotoTagAssignment
from app.schemas.photos import (
    CreateTagRequest,
    SetPhotoTagsRequest,
    TagList,
    TagPublic,
)
from app.services import photos_photo_repo, photos_tag_repo
from app.services.photos_acl import require_photo_permission

from ._common import _slugify

router = APIRouter()


@router.get("/tags", response_model=TagList)
async def list_tags(
    db: DbDep, user: CurrentUser, q: str = Query(default="", max_length=100)
) -> TagList:
    rows = await photos_tag_repo.list_tags_with_usage(db, q)
    items = [
        TagPublic(
            id=row.PhotoTag.id,
            name=row.PhotoTag.name,
            slug=row.PhotoTag.slug,
            usage_count=row.usage_count or 0,
        )
        for row in rows
    ]
    return TagList(items=items)


@router.post("/tags", response_model=TagPublic, status_code=201)
async def create_tag(data: CreateTagRequest, db: DbDep, user: CurrentUser) -> TagPublic:
    if user.role not in (PERM_EDITOR, "admin"):
        raise HTTPException(status_code=403, detail="Editor or admin required")
    slug = _slugify(data.name)
    existing = await photos_tag_repo.find_tag_by_name(db, data.name)
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")
    tag = PhotoTag(name=data.name, slug=slug)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return TagPublic(id=tag.id, name=tag.name, slug=tag.slug, usage_count=0)


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: uuid.UUID, db: DbDep, user: AdminDep) -> Response:
    await photos_tag_repo.delete_tag(db, tag_id)
    await db.commit()
    return Response(status_code=204)


@router.get("/{photo_id}/tags", response_model=list[TagPublic])
async def get_photo_tags(
    photo_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> list[TagPublic]:
    photo = await photos_photo_repo.fetch_active_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_VIEWER, db, redis)
    tags = await photos_tag_repo.list_photo_tags(db, photo_id)
    return [TagPublic(id=t.id, name=t.name, slug=t.slug) for t in tags]


@router.patch("/{photo_id}/tags", response_model=list[TagPublic])
async def set_photo_tags(
    photo_id: uuid.UUID, data: SetPhotoTagsRequest, db: DbDep, user: CurrentUser, redis: RedisDep
) -> list[TagPublic]:
    photo = await photos_photo_repo.fetch_active_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_UPLOADER, db, redis)
    await photos_tag_repo.clear_photo_tags(db, photo_id)
    for tag_id in data.tag_ids:
        tag_exists = await photos_tag_repo.get_tag(db, tag_id)
        if tag_exists:
            db.add(PhotoTagAssignment(photo_id=photo_id, tag_id=tag_id))
    await db.commit()
    tags = await photos_tag_repo.list_photo_tags(db, photo_id)
    return [TagPublic(id=t.id, name=t.name, slug=t.slug) for t in tags]
