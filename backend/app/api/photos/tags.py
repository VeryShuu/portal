"""Tag CRUD and per-photo tag management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import delete, func, select

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_EDITOR, PERM_UPLOADER, PERM_VIEWER
from app.models.photos import Photo, PhotoTag, PhotoTagAssignment
from app.schemas.photos import (
    CreateTagRequest,
    SetPhotoTagsRequest,
    TagList,
    TagPublic,
)
from app.services.photos_acl import require_photo_permission

from ._common import _slugify

router = APIRouter()


@router.get("/tags", response_model=TagList)
async def list_tags(
    db: DbDep, user: CurrentUser, q: str = Query(default="", max_length=100)
) -> TagList:
    stmt = (
        select(PhotoTag, func.count(PhotoTagAssignment.photo_id).label("usage_count"))
        .outerjoin(PhotoTagAssignment, PhotoTagAssignment.tag_id == PhotoTag.id)
        .group_by(PhotoTag.id)
        .order_by(PhotoTag.name)
    )
    if q:
        stmt = stmt.where(PhotoTag.name.ilike(f"%{q}%"))
    res = await db.execute(stmt)
    items = [
        TagPublic(
            id=row.PhotoTag.id,
            name=row.PhotoTag.name,
            slug=row.PhotoTag.slug,
            usage_count=row.usage_count or 0,
        )
        for row in res.all()
    ]
    return TagList(items=items)


@router.post("/tags", response_model=TagPublic, status_code=201)
async def create_tag(data: CreateTagRequest, db: DbDep, user: CurrentUser) -> TagPublic:
    if user.role not in (PERM_EDITOR, "admin"):
        raise HTTPException(status_code=403, detail="Editor or admin required")
    slug = _slugify(data.name)
    existing = await db.scalar(select(PhotoTag).where(PhotoTag.name == data.name))
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")
    tag = PhotoTag(name=data.name, slug=slug)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return TagPublic(id=tag.id, name=tag.name, slug=tag.slug, usage_count=0)


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: uuid.UUID, db: DbDep, user: AdminDep) -> Response:
    await db.execute(delete(PhotoTag).where(PhotoTag.id == tag_id))
    await db.commit()
    return Response(status_code=204)


@router.get("/{photo_id}/tags", response_model=list[TagPublic])
async def get_photo_tags(
    photo_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> list[TagPublic]:
    res_photo = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None))
    )
    photo = res_photo.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_VIEWER, db, redis)
    res = await db.execute(
        select(PhotoTag)
        .join(PhotoTagAssignment, PhotoTagAssignment.tag_id == PhotoTag.id)
        .where(PhotoTagAssignment.photo_id == photo_id)
        .order_by(PhotoTag.name)
    )
    return [TagPublic(id=t.id, name=t.name, slug=t.slug) for t in res.scalars().all()]


@router.patch("/{photo_id}/tags", response_model=list[TagPublic])
async def set_photo_tags(
    photo_id: uuid.UUID, data: SetPhotoTagsRequest, db: DbDep, user: CurrentUser, redis: RedisDep
) -> list[TagPublic]:
    res_photo = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None))
    )
    photo = res_photo.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_UPLOADER, db, redis)
    await db.execute(delete(PhotoTagAssignment).where(PhotoTagAssignment.photo_id == photo_id))
    for tag_id in data.tag_ids:
        tag_exists = await db.scalar(select(PhotoTag).where(PhotoTag.id == tag_id))
        if tag_exists:
            db.add(PhotoTagAssignment(photo_id=photo_id, tag_id=tag_id))
    await db.commit()
    res = await db.execute(
        select(PhotoTag)
        .join(PhotoTagAssignment, PhotoTagAssignment.tag_id == PhotoTag.id)
        .where(PhotoTagAssignment.photo_id == photo_id)
        .order_by(PhotoTag.name)
    )
    return [TagPublic(id=t.id, name=t.name, slug=t.slug) for t in res.scalars().all()]
