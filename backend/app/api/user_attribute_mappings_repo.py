"""Data-access helpers for the user-attribute-mapping admin endpoints.

Keeps raw SQL (``select``/``text``/``update``) out of the HTTP route handlers.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_attribute_mapping import UserAttributeMapping


async def list_enabled_non_fullname_mappings(
    db: AsyncSession,
) -> Sequence[UserAttributeMapping]:
    stmt = (
        select(UserAttributeMapping)
        .where(
            UserAttributeMapping.enabled.is_(True),
            UserAttributeMapping.is_full_name_source.is_(False),
        )
        .order_by(UserAttributeMapping.sort_order, UserAttributeMapping.label_ru)
    )
    return (await db.execute(stmt)).scalars().all()


async def list_all_mappings(db: AsyncSession) -> Sequence[UserAttributeMapping]:
    stmt = select(UserAttributeMapping).order_by(
        UserAttributeMapping.sort_order, UserAttributeMapping.label_ru
    )
    return (await db.execute(stmt)).scalars().all()


async def count_mappings(db: AsyncSession) -> int:
    total = (
        await db.execute(select(func.count()).select_from(UserAttributeMapping))
    ).scalar_one()
    return int(total)


async def discover_attribute_keys(db: AsyncSession) -> Sequence[Any]:
    sql = (
        select(
            func.jsonb_object_keys(User.attributes).label("attr_key"),
            func.count().label("occurrences"),
        )
        .group_by("attr_key")
        .order_by(func.count().desc(), "attr_key")
    )
    return (await db.execute(sql)).all()


async def list_existing_attr_keys(db: AsyncSession) -> set[str]:
    return {r[0] for r in (await db.execute(select(UserAttributeMapping.attr_key))).all()}


async def sample_attribute_value(db: AsyncSession, key: str) -> str | None:
    sample_sql = (
        select(User.attributes[key].astext)
        .where(User.attributes[key].astext.isnot(None))
        .limit(1)
    )
    return (await db.execute(sample_sql)).scalar_one_or_none()


async def find_mapping_by_attr_key(
    db: AsyncSession, attr_key: str
) -> UserAttributeMapping | None:
    return (
        await db.execute(
            select(UserAttributeMapping).where(UserAttributeMapping.attr_key == attr_key)
        )
    ).scalar_one_or_none()


async def find_mapping_by_id(
    db: AsyncSession, mapping_id: uuid.UUID
) -> UserAttributeMapping | None:
    return (
        await db.execute(
            select(UserAttributeMapping).where(UserAttributeMapping.id == mapping_id)
        )
    ).scalar_one_or_none()


async def clear_full_name_source(
    db: AsyncSession, *, exclude_id: uuid.UUID | None = None
) -> None:
    stmt = update(UserAttributeMapping).where(
        UserAttributeMapping.is_full_name_source.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(UserAttributeMapping.id != exclude_id)
    await db.execute(stmt.values(is_full_name_source=False, updated_at=datetime.now(UTC)))


async def backfill_full_name_from_attribute(db: AsyncSession, attr_key: str) -> int:
    """Перезаписать users.full_name из users.attributes[attr_key] для всех живых пользователей.

    Возвращает количество обновлённых строк.  Используется когда админ помечает
    атрибут как «источник ФИО», чтобы не ждать ближайшего цикла KC-синка.
    Пустые/отсутствующие значения атрибута строки не трогают — full_name остаётся
    как было (там лежит firstName + lastName из предыдущей синхронизации).
    """
    cursor = cast(
        CursorResult[tuple[()]],
        await db.execute(
            text(
                """
            UPDATE users
            SET full_name = btrim(attributes->>:k),
                updated_at = NOW()
            WHERE deleted_at IS NULL
              AND attributes ? :k
              AND attributes->>:k IS NOT NULL
              AND btrim(attributes->>:k) <> ''
              AND full_name IS DISTINCT FROM btrim(attributes->>:k)
            """
            ),
            {"k": attr_key},
        ),
    )
    return int(cursor.rowcount or 0)
