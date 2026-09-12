from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.api import user_attribute_mappings_repo as repo
from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.logging import get_logger
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
from app.services.audit import make_audit_emitter

router = APIRouter(prefix="/user-attribute-mappings", tags=["user-attribute-mappings"])
logger = get_logger(__name__)

_emit_audit = make_audit_emitter("user_attribute_mapping")


# Ключи Keycloak-атрибутов, которые синхронизация воркера уже мапит в нативные
# колонки users.* (см. app/worker/tasks/news.py::sync_users_from_keycloak).
# Их нет смысла показывать в /discover, т.к. они уже отображаются в карточке
# пользователя в блоке "Личные данные" и повторное добавление через JSONB
# создаст визуальный дубль.
_RESERVED_NATIVE_ATTR_KEYS: frozenset[str] = frozenset(
    {
        # users.email / users.full_name
        "email",
        "firstName",
        "lastName",
        "name",
        # users.department
        "department",
        # users.position
        "job_title",
        "post",
        "title",
        # users.phone
        "phone",
    }
)


@router.get(
    "/schema",
    response_model=UserAttributeMappingSchemaList,
    summary="Публичная схема атрибутов для отображения в карточке пользователя",
)
async def get_attributes_schema(
    user: CurrentUser,
    db: DbDep,
) -> UserAttributeMappingSchemaList:
    # Атрибут, помеченный как «источник ФИО», в карточку не возвращаем — его
    # значение уже отображается как канонический users.full_name в шапке
    # профиля и в строке «ФИО» (которая формируется из колонки full_name, а
    # не из JSONB).  Иначе в карточке появлялись бы два одинаковых поля.
    rows = await repo.list_enabled_non_fullname_mappings(db)
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
    rows = await repo.list_all_mappings(db)
    total = await repo.count_mappings(db)
    return UserAttributeMappingList(
        items=[UserAttributeMappingPublic.model_validate(r) for r in rows],
        total=total,
    )


@router.get(
    "/discover",
    response_model=DiscoverAttributesResponse,
    summary="Найти ключи атрибутов в users.attributes (admin)",
)
async def discover_attributes(admin: AdminDep, db: DbDep) -> DiscoverAttributesResponse:
    rows = await repo.discover_attribute_keys(db)

    existing_keys = await repo.list_existing_attr_keys(db)

    items: list[DiscoverAttributeItem] = []
    for r in rows:
        key = r.attr_key
        if not isinstance(key, str) or not key:
            continue
        if key in existing_keys:
            continue
        if key in _RESERVED_NATIVE_ATTR_KEYS:
            continue
        sample = await repo.sample_attribute_value(db, key)
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
    if body.attr_key in _RESERVED_NATIVE_ATTR_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Attribute '{body.attr_key}' is already represented by a native user "
                "field and is shown in the profile automatically"
            ),
        )
    exists = await repo.find_mapping_by_attr_key(db, body.attr_key)
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mapping with this attr_key already exists",
        )

    if body.is_full_name_source:
        await repo.clear_full_name_source(db)

    mapping = UserAttributeMapping(
        attr_key=body.attr_key,
        label_ru=body.label_ru,
        label_en=body.label_en,
        sort_order=body.sort_order,
        enabled=body.enabled,
        is_full_name_source=body.is_full_name_source,
    )
    db.add(mapping)
    await db.flush()

    backfilled = 0
    if mapping.is_full_name_source and mapping.enabled:
        backfilled = await repo.backfill_full_name_from_attribute(db, mapping.attr_key)

    await db.commit()
    await db.refresh(mapping)
    if backfilled:
        logger.info(
            "user_attribute_mapping.full_name_backfilled",
            mapping_id=str(mapping.id),
            attr_key=mapping.attr_key,
            updated_rows=backfilled,
        )
    await _emit_audit(
        redis,
        event_type="user_attribute_mappings.created",
        user_id=str(admin.id),
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
    mapping = await repo.find_mapping_by_id(db, mapping_id)
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")

    changes = body.model_dump(exclude_unset=True)
    if changes.get("is_full_name_source") is True:
        await repo.clear_full_name_source(db, exclude_id=mapping.id)
    for field, value in changes.items():
        setattr(mapping, field, value)
    mapping.updated_at = datetime.now(UTC)
    await db.flush()

    backfilled = 0
    if (
        mapping.is_full_name_source
        and mapping.enabled
        and ("is_full_name_source" in changes or "enabled" in changes)
    ):
        backfilled = await repo.backfill_full_name_from_attribute(db, mapping.attr_key)

    await db.commit()
    await db.refresh(mapping)
    if backfilled:
        logger.info(
            "user_attribute_mapping.full_name_backfilled",
            mapping_id=str(mapping.id),
            attr_key=mapping.attr_key,
            updated_rows=backfilled,
        )
    await _emit_audit(
        redis,
        event_type="user_attribute_mappings.updated",
        user_id=str(admin.id),
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
    mapping = await repo.find_mapping_by_id(db, mapping_id)
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")

    attr_key = mapping.attr_key
    await db.delete(mapping)
    await db.commit()
    await _emit_audit(
        redis,
        event_type="user_attribute_mappings.deleted",
        user_id=str(admin.id),
        resource_id=str(mapping_id),
        metadata={"attr_key": attr_key},
    )
    logger.info(
        "user_attribute_mapping.deleted",
        mapping_id=str(mapping_id),
        admin=str(admin.id),
    )
