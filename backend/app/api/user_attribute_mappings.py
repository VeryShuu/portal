from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.logging import get_logger
from app.models.user import User
from app.models.user_attribute_mapping import UserAttributeMapping
from app.schemas.user_attribute_mapping import (
    CreateUserAttributeMappingRequest,
    DiscoverAttributeItem,
    DiscoverAttributesResponse,
    UpdateUserAttributeMappingRequest,
    UserAttributeMappingList,
    UserAttributeMappingPublic,
    UserAttributeMappingSchema,
    UserAttributeMappingSchemaList,
)
from app.services.audit import push_audit_event

router = APIRouter(prefix="/user-attribute-mappings", tags=["user-attribute-mappings"])
logger = get_logger(__name__)


@router.get(
    "/schema",
    response_model=UserAttributeMappingSchemaList,
    summary="Публичная схема атрибутов для отображения в карточке пользователя",
)
async def get_attributes_schema(
    user: CurrentUser,
    db: DbDep,
) -> UserAttributeMappingSchemaList:
    stmt = (
        select(UserAttributeMapping)
        .where(UserAttributeMapping.enabled.is_(True))
        .order_by(UserAttributeMapping.sort_order, UserAttributeMapping.label_ru)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return UserAttributeMappingSchemaList(
        items=[
            UserAttributeMappingSchema(
                attr_key=r.attr_key,
                label_ru=r.label_ru,
                label_en=r.label_en,
                sort_order=r.sort_order,
            )
            for r in rows
        ]
    )


@router.get(
    "",
    response_model=UserAttributeMappingList,
    summary="Список маппингов атрибутов (admin)",
)
async def list_mappings(admin: AdminDep, db: DbDep) -> UserAttributeMappingList:
    stmt = select(UserAttributeMapping).order_by(
        UserAttributeMapping.sort_order, UserAttributeMapping.label_ru
    )
    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(select(func.count()).select_from(UserAttributeMapping))).scalar_one()
    return UserAttributeMappingList(items=list(rows), total=total)


@router.get(
    "/discover",
    response_model=DiscoverAttributesResponse,
    summary="Найти ключи атрибутов в users.attributes (admin)",
)
async def discover_attributes(admin: AdminDep, db: DbDep) -> DiscoverAttributesResponse:
    sql = select(
        func.jsonb_object_keys(User.attributes).label("attr_key"),
        func.count().label("occurrences"),
    ).group_by("attr_key").order_by(func.count().desc(), "attr_key")
    rows = (await db.execute(sql)).all()

    existing_keys = {
        r[0]
        for r in (
            await db.execute(select(UserAttributeMapping.attr_key))
        ).all()
    }

    items: list[DiscoverAttributeItem] = []
    for r in rows:
        key = r.attr_key
        if not isinstance(key, str) or not key:
            continue
        if key in existing_keys:
            continue
        sample_sql = (
            select(User.attributes[key].astext)
            .where(User.attributes[key].astext.isnot(None))
            .limit(1)
        )
        sample = (await db.execute(sample_sql)).scalar_one_or_none()
        items.append(
            DiscoverAttributeItem(
                attr_key=key,
                sample=str(sample)[:200] if sample is not None else None,
                occurrences=int(r.occurrences),
            )
        )
    return DiscoverAttributesResponse(items=items)


@router.post(
    "",
    response_model=UserAttributeMappingPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Создать маппинг атрибута (admin)",
)
async def create_mapping(
    body: CreateUserAttributeMappingRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> UserAttributeMapping:
    exists = (
        await db.execute(
            select(UserAttributeMapping).where(
                UserAttributeMapping.attr_key == body.attr_key
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mapping with this attr_key already exists",
        )

    mapping = UserAttributeMapping(
        attr_key=body.attr_key,
        label_ru=body.label_ru,
        label_en=body.label_en,
        sort_order=body.sort_order,
        enabled=body.enabled,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    await push_audit_event(
        redis,
        event_type="user_attribute_mappings.created",
        user_id=str(admin.id),
        resource_type="user_attribute_mapping",
        resource_id=str(mapping.id),
        metadata={"attr_key": mapping.attr_key},
    )
    logger.info(
        "user_attribute_mapping.created",
        mapping_id=str(mapping.id),
        attr_key=mapping.attr_key,
        admin=str(admin.id),
    )
    return mapping


@router.put(
    "/{mapping_id}",
    response_model=UserAttributeMappingPublic,
    summary="Обновить маппинг (admin)",
)
async def update_mapping(
    mapping_id: uuid.UUID,
    body: UpdateUserAttributeMappingRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> UserAttributeMapping:
    mapping = (
        await db.execute(
            select(UserAttributeMapping).where(UserAttributeMapping.id == mapping_id)
        )
    ).scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(mapping, field, value)
    mapping.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(mapping)
    await push_audit_event(
        redis,
        event_type="user_attribute_mappings.updated",
        user_id=str(admin.id),
        resource_type="user_attribute_mapping",
        resource_id=str(mapping.id),
        metadata={"fields": sorted(changes.keys())},
    )
    logger.info(
        "user_attribute_mapping.updated",
        mapping_id=str(mapping.id),
        admin=str(admin.id),
    )
    return mapping


@router.delete(
    "/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить маппинг (admin)",
)
async def delete_mapping(
    mapping_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    mapping = (
        await db.execute(
            select(UserAttributeMapping).where(UserAttributeMapping.id == mapping_id)
        )
    ).scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")

    attr_key = mapping.attr_key
    await db.delete(mapping)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="user_attribute_mappings.deleted",
        user_id=str(admin.id),
        resource_type="user_attribute_mapping",
        resource_id=str(mapping_id),
        metadata={"attr_key": attr_key},
    )
    logger.info(
        "user_attribute_mapping.deleted",
        mapping_id=str(mapping_id),
        admin=str(admin.id),
    )
