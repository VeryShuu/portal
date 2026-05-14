"""Users data access layer."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


def _build_list_conditions(q: str | None, department: str | None) -> list[Any]:
    conditions: list[Any] = [User.deleted_at.is_(None)]
    if q:
        pattern = f"%{q}%"
        conditions.append(User.full_name.ilike(pattern) | User.email.ilike(pattern))
    if department:
        conditions.append(User.department == department)
    return conditions


async def count_users(
    db: AsyncSession, *, q: str | None, department: str | None
) -> int:
    conditions = _build_list_conditions(q, department)
    res = await db.execute(select(func.count(User.id)).where(*conditions))
    return int(res.scalar_one())


async def list_users_page(
    db: AsyncSession,
    *,
    q: str | None,
    department: str | None,
    page: int,
    page_size: int,
) -> Sequence[User]:
    conditions = _build_list_conditions(q, department)
    stmt = (
        select(User)
        .where(*conditions)
        .order_by(User.full_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


async def fetch_active_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    return res.scalar_one_or_none()


async def fetch_user_any(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def find_active_by_email(db: AsyncSession, email: str) -> User | None:
    res = await db.execute(
        select(User).where(
            func.lower(User.email) == email.lower(),
            User.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


async def update_user_fields(
    db: AsyncSession, user_id: uuid.UUID, values: dict
) -> None:
    await db.execute(update(User).where(User.id == user_id).values(**values))


async def insert_local_user(
    db: AsyncSession,
    *,
    email: str,
    full_name: str,
    password_hash: str,
    role: str,
) -> User:
    now = datetime.now(UTC)
    stmt = (
        pg_insert(User)
        .values(
            email=email,
            full_name=full_name,
            auth_source="local",
            password_hash=password_hash,
            role=role,
            updated_at=now,
        )
        .returning(User)
    )
    res = await db.execute(stmt)
    return res.scalars().one()


async def count_news_versions_for_editor(
    db: AsyncSession, user_id: uuid.UUID
) -> int:
    val = await db.scalar(
        text("SELECT COUNT(*) FROM news_versions WHERE editor_id = :uid"),
        {"uid": user_id},
    )
    return int(val or 0)


async def soft_delete_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    await db.execute(
        update(User).where(User.id == user_id).values(deleted_at=now, updated_at=now)
    )
