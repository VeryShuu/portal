"""Integration-тесты route-хендлеров ``app/api/user_attribute_mappings.py``.

Поднимают все 5 эндпойнтов модуля (schema/list/discover/create/update/delete)
через прямой вызов route-функций на реальной БД (стиль ``test_photos_api.py``).
Redis-зависимости (audit-emitter) мокаются — они не относятся к тестируемой логике.

До этого PR модуль покрывался только на 30% (authz-проверки через no-op _fake_db
в unit-тестах). Здесь — бизнес-логика на реальной PG: CRUD, conflict (409),
reserved-keys (400), full_name_source toggle + backfill, discover-фильтрация.

Требует INTEGRATION_DB=true и запущенного Postgres.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.user import User
from app.models.user_attribute_mapping import UserAttributeMapping

pytestmark = pytest.mark.asyncio


def _redis_mock() -> AsyncMock:
    """Redis-stub: audit-emitter пишет lpush/hset — нам важен сам факт вызова."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.set = AsyncMock()
    r.delete = AsyncMock()
    r.rpush = AsyncMock()  # audit-emitter пишет через rpush (AUDIT_QUEUE_KEY)
    r.ltrim = AsyncMock()
    r.expire = AsyncMock()
    return r


def _request() -> SimpleNamespace:
    """Request-stub: route-хендлеры читают request.client.host (audit)."""
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"), app=SimpleNamespace(state=SimpleNamespace())
    )


async def _seed_mapping(
    session,
    *,
    attr_key: str | None = None,
    label_ru: str = "Город",
    label_en: str | None = None,
    sort_order: int = 0,
    enabled: bool = True,
    is_full_name_source: bool = False,
) -> UserAttributeMapping:
    m = UserAttributeMapping(
        attr_key=attr_key or f"key-{uuid.uuid4().hex[:6]}",
        label_ru=label_ru,
        label_en=label_en,
        sort_order=sort_order,
        enabled=enabled,
        is_full_name_source=is_full_name_source,
    )
    session.add(m)
    await session.flush()
    await session.refresh(m)
    return m


async def _seed_user(session, *, attributes: dict | None = None, full_name: str = "User") -> User:
    u = User(
        email=f"uam-{uuid.uuid4().hex[:8]}@portal.local",
        full_name=full_name,
        role="reader",
        auth_source="local",
        current_status="working",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        attributes=attributes or {},
    )
    session.add(u)
    await session.flush()
    return u


# ── GET /schema ──────────────────────────────────────────────────────────────


class TestGetAttributesSchema:
    async def test_returns_only_enabled_non_fullname(self, real_db_session, real_user):
        # enabled non-fullname → попадает в schema
        await _seed_mapping(real_db_session, attr_key="city", label_ru="Город")
        # disabled → НЕ попадает
        await _seed_mapping(real_db_session, attr_key="floor", enabled=False)
        # is_full_name_source → НЕ попадает (значение уже в users.full_name)
        await _seed_mapping(real_db_session, attr_key="displayName", is_full_name_source=True)

        from app.api.user_attribute_mappings import get_attributes_schema

        result = await get_attributes_schema(real_user, real_db_session)

        keys = {i.attr_key for i in result.items}
        assert keys == {"city"}
        item = next(i for i in result.items if i.attr_key == "city")
        assert item.label_ru == "Город"
        assert item.label_en is None
        assert item.sort_order == 0

    async def test_empty_when_no_mappings(self, real_db_session, real_user):
        from app.api.user_attribute_mappings import get_attributes_schema

        result = await get_attributes_schema(real_user, real_db_session)
        assert result.items == []


# ── GET "" (list, admin) ────────────────────────────────────────────────────


class TestListMappings:
    async def test_returns_all_with_total(self, real_db_session, real_admin):
        await _seed_mapping(real_db_session, attr_key="a1", sort_order=2)
        await _seed_mapping(real_db_session, attr_key="a2", sort_order=1)

        from app.api.user_attribute_mappings import list_mappings

        result = await list_mappings(real_admin, real_db_session)

        keys = [i.attr_key for i in result.items]
        assert set(keys) == {"a1", "a2"}
        # сортировка по sort_order → a2 (1) раньше a1 (2)
        assert keys == ["a2", "a1"]
        assert result.total == 2


# ── GET /discover ────────────────────────────────────────────────────────────


class TestDiscoverAttributes:
    async def test_discovers_keys_excluding_existing_and_reserved(
        self, real_db_session, real_admin
    ):
        # Пользователь с атрибутами: city (новый), department (reserved), displayName (новый)
        await _seed_user(
            real_db_session,
            attributes={"city": "Москва", "department": "IT", "displayName": "Иван"},
        )
        # уже существующий маппинг на city → city не должен попасть в discover
        await _seed_mapping(real_db_session, attr_key="city", label_ru="Город")

        from app.api.user_attribute_mappings import discover_attributes

        result = await discover_attributes(real_admin, real_db_session)

        keys = {i.attr_key for i in result.items}
        # city — уже замаплен (existing), department — reserved → исключаются.
        # остаётся только displayName.
        assert keys == {"displayName"}
        item = next(i for i in result.items if i.attr_key == "displayName")
        assert item.sample == "Иван"
        assert item.occurrences == 1

    async def test_empty_when_all_keys_reserved_or_existing(self, real_db_session, real_admin):
        # только reserved-ключи
        await _seed_user(real_db_session, attributes={"email": "x@y.z", "phone": "123"})

        from app.api.user_attribute_mappings import discover_attributes

        result = await discover_attributes(real_admin, real_db_session)
        assert result.items == []


# ── POST "" (create, admin) ──────────────────────────────────────────────────


class TestCreateMapping:
    async def test_happy_path(self, real_db_session, real_admin):
        from app.api.user_attribute_mappings import create_mapping
        from app.schemas.user_attribute_mapping import CreateUserAttributeMappingRequest

        redis = _redis_mock()
        body = CreateUserAttributeMappingRequest(
            attr_key="office", label_ru="Офис", label_en="Office", sort_order=5
        )

        mapping = await create_mapping(body, real_admin, real_db_session, redis)

        assert mapping.id is not None
        assert mapping.attr_key == "office"
        assert mapping.label_ru == "Офис"
        assert mapping.label_en == "Office"
        assert mapping.sort_order == 5
        assert mapping.enabled is True
        assert mapping.is_full_name_source is False
        # audit-emitter вызван (created → rpush в AUDIT_QUEUE_KEY)
        assert redis.rpush.await_count >= 1

    async def test_reserved_attr_key_rejected_400(self, real_db_session, real_admin):
        from app.api.user_attribute_mappings import create_mapping
        from app.schemas.user_attribute_mapping import CreateUserAttributeMappingRequest

        body = CreateUserAttributeMappingRequest(attr_key="email", label_ru="Email")
        with pytest.raises(HTTPException) as exc:
            await create_mapping(body, real_admin, real_db_session, _redis_mock())
        assert exc.value.status_code == 400
        assert "native user field" in exc.value.detail

    async def test_duplicate_attr_key_conflict_409(self, real_db_session, real_admin):
        from app.api.user_attribute_mappings import create_mapping
        from app.schemas.user_attribute_mapping import CreateUserAttributeMappingRequest

        await _seed_mapping(real_db_session, attr_key="city", label_ru="Город")

        body = CreateUserAttributeMappingRequest(attr_key="city", label_ru="Город2")
        with pytest.raises(HTTPException) as exc:
            await create_mapping(body, real_admin, real_db_session, _redis_mock())
        assert exc.value.status_code == 409
        assert "already exists" in exc.value.detail

    async def test_full_name_source_clears_previous_and_backfills(
        self, real_db_session, real_admin
    ):
        # Существующий full_name_source-маппинг + пользователь с этим атрибутом
        await _seed_mapping(real_db_session, attr_key="oldName", is_full_name_source=True)
        await _seed_user(
            real_db_session,
            attributes={"newName": "Новое Имя"},
            full_name="Старое Имя",
        )

        from app.api.user_attribute_mappings import create_mapping
        from app.schemas.user_attribute_mapping import CreateUserAttributeMappingRequest

        body = CreateUserAttributeMappingRequest(
            attr_key="newName", label_ru="ФИО", is_full_name_source=True
        )
        mapping = await create_mapping(body, real_admin, real_db_session, _redis_mock())

        assert mapping.is_full_name_source is True
        # новый стал full_name_source
        refetched = (
            await real_db_session.execute(
                select(UserAttributeMapping).where(UserAttributeMapping.attr_key == "newName")
            )
        ).scalar_one()
        assert refetched.is_full_name_source is True
        # старый сброшен (clear_full_name_source)
        old = (
            await real_db_session.execute(
                select(UserAttributeMapping).where(UserAttributeMapping.attr_key == "oldName")
            )
        ).scalar_one()
        assert old.is_full_name_source is False
        # backfill: users.full_name перезаписан из attributes['newName']
        user = (
            await real_db_session.execute(
                select(User).where(User.attributes["newName"].astext == "Новое Имя")
            )
        ).scalar_one()
        assert user.full_name == "Новое Имя"


# ── PUT "/{mapping_id}" (update, admin) ─────────────────────────────────────


class TestUpdateMapping:
    async def test_update_fields(self, real_db_session, real_admin):
        existing = await _seed_mapping(
            real_db_session, attr_key="floor", label_ru="Этаж", sort_order=0
        )

        from app.api.user_attribute_mappings import update_mapping
        from app.schemas.user_attribute_mapping import UpdateUserAttributeMappingRequest

        body = UpdateUserAttributeMappingRequest(label_ru="Этаж офиса", sort_order=10)
        updated = await update_mapping(
            existing.id, body, real_admin, real_db_session, _redis_mock()
        )

        assert updated.label_ru == "Этаж офиса"
        assert updated.sort_order == 10
        assert updated.attr_key == "floor"  # не менялся

    async def test_update_not_found_404(self, real_db_session, real_admin):
        from app.api.user_attribute_mappings import update_mapping
        from app.schemas.user_attribute_mapping import UpdateUserAttributeMappingRequest

        body = UpdateUserAttributeMappingRequest(enabled=False)
        with pytest.raises(HTTPException) as exc:
            await update_mapping(uuid.uuid4(), body, real_admin, real_db_session, _redis_mock())
        assert exc.value.status_code == 404

    async def test_full_name_source_toggle_clears_others(self, real_db_session, real_admin):
        # два маппинга, none is full_name_source
        other = await _seed_mapping(real_db_session, attr_key="other", is_full_name_source=True)
        target = await _seed_mapping(real_db_session, attr_key="target")

        from app.api.user_attribute_mappings import update_mapping
        from app.schemas.user_attribute_mapping import UpdateUserAttributeMappingRequest

        body = UpdateUserAttributeMappingRequest(is_full_name_source=True)
        await update_mapping(target.id, body, real_admin, real_db_session, _redis_mock())

        # target стал full_name_source, other — сброшен
        other_ref = (
            await real_db_session.execute(
                select(UserAttributeMapping).where(UserAttributeMapping.id == other.id)
            )
        ).scalar_one()
        assert other_ref.is_full_name_source is False
        target_ref = (
            await real_db_session.execute(
                select(UserAttributeMapping).where(UserAttributeMapping.id == target.id)
            )
        ).scalar_one()
        assert target_ref.is_full_name_source is True


# ── DELETE "/{mapping_id}" (admin) ───────────────────────────────────────────


class TestDeleteMapping:
    async def test_delete_happy(self, real_db_session, real_admin):
        existing = await _seed_mapping(real_db_session, attr_key="todelete")

        from app.api.user_attribute_mappings import delete_mapping

        result = await delete_mapping(existing.id, real_admin, real_db_session, _redis_mock())
        assert result is None  # 204 No Content

        # запись удалена из БД
        refetched = (
            await real_db_session.execute(
                select(UserAttributeMapping).where(UserAttributeMapping.id == existing.id)
            )
        ).scalar_one_or_none()
        assert refetched is None

    async def test_delete_not_found_404(self, real_db_session, real_admin):
        from app.api.user_attribute_mappings import delete_mapping

        with pytest.raises(HTTPException) as exc:
            await delete_mapping(uuid.uuid4(), real_admin, real_db_session, _redis_mock())
        assert exc.value.status_code == 404
