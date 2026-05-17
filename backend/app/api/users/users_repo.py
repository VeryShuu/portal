"""Users data access layer."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff_order import StaffDepartmentOrder
from app.models.user import User


def _build_list_conditions(
    q: str | None,
    department: str | None,
    office: str | None = None,
    *,
    include_hidden: bool = True,
) -> list[Any]:
    conditions: list[Any] = [User.deleted_at.is_(None)]
    if not include_hidden:
        conditions.append(User.staff_hidden.is_(False))
    if q:
        pattern = f"%{q}%"
        conditions.append(
            User.full_name.ilike(pattern)
            | User.email.ilike(pattern)
            | User.position.ilike(pattern)
            | User.phone.ilike(pattern)
            | User.attributes["internal_phone"].astext.ilike(pattern)
            | User.attributes["mobile"].astext.ilike(pattern)
        )
    if department:
        conditions.append(User.department == department)
    if office:
        conditions.append(User.attributes["city"].astext == office)
    return conditions


def _build_order(sort: str) -> tuple[Any, ...]:
    if sort == "department":
        return (User.department.asc().nullslast(), User.full_name.asc())
    if sort == "staff_custom":
        # Order by department's custom sort_order (NULLS LAST → end alphabetically),
        # then department name, then user's per-department sort_order
        # (NULLS LAST → end alphabetically), then full_name.
        return (
            StaffDepartmentOrder.sort_order.asc().nullslast(),
            User.department.asc().nullslast(),
            User.staff_sort_order.asc().nullslast(),
            User.full_name.asc(),
        )
    return (User.full_name.asc(),)


def _select_users(sort: str):
    stmt = select(User)
    if sort == "staff_custom":
        stmt = stmt.outerjoin(
            StaffDepartmentOrder,
            StaffDepartmentOrder.department == User.department,
        )
    return stmt


async def count_users(
    db: AsyncSession,
    *,
    q: str | None,
    department: str | None,
    office: str | None = None,
    include_hidden: bool = True,
) -> int:
    conditions = _build_list_conditions(
        q, department, office, include_hidden=include_hidden
    )
    res = await db.execute(select(func.count(User.id)).where(*conditions))
    return int(res.scalar_one())


async def list_users_page(
    db: AsyncSession,
    *,
    q: str | None,
    department: str | None,
    page: int,
    page_size: int,
    office: str | None = None,
    sort: str = "full_name",
    include_hidden: bool = True,
) -> Sequence[User]:
    conditions = _build_list_conditions(
        q, department, office, include_hidden=include_hidden
    )
    stmt = (
        _select_users(sort)
        .where(*conditions)
        .order_by(*_build_order(sort))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


async def list_departments(
    db: AsyncSession, *, ordered: bool = False
) -> list[str]:
    res = await db.execute(
        select(User.department)
        .where(
            User.deleted_at.is_(None),
            User.department.isnot(None),
            func.length(func.trim(User.department)) > 0,
        )
        .distinct()
        .order_by(User.department.asc())
    )
    items = [row for row in res.scalars().all() if row and row.strip()]
    if not ordered:
        return items

    order_res = await db.execute(
        select(StaffDepartmentOrder.department, StaffDepartmentOrder.sort_order)
        .order_by(StaffDepartmentOrder.sort_order.asc())
    )
    order_map = {dept: idx for dept, idx in order_res.all()}

    def sort_key(d: str) -> tuple[int, int, str]:
        if d in order_map:
            return (0, order_map[d], d)
        return (1, 0, d)

    items.sort(key=sort_key)
    return items


async def list_offices(db: AsyncSession) -> list[str]:
    office_expr = User.attributes["city"].astext
    res = await db.execute(
        select(office_expr)
        .where(
            User.deleted_at.is_(None),
            office_expr.isnot(None),
            func.length(func.trim(office_expr)) > 0,
        )
        .distinct()
        .order_by(office_expr.asc())
    )
    return [row for row in res.scalars().all() if row and row.strip()]


async def stream_users(
    db: AsyncSession,
    *,
    q: str | None,
    department: str | None,
    office: str | None,
    sort: str,
    include_hidden: bool = True,
) -> AsyncIterator[User]:
    conditions = _build_list_conditions(
        q, department, office, include_hidden=include_hidden
    )
    stmt = (
        _select_users(sort)
        .where(*conditions)
        .order_by(*_build_order(sort))
        .execution_options(yield_per=500)
    )
    res = await db.stream(stmt)
    async for partition in res.scalars().partitions(500):
        for user in partition:
            yield user


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


# ─────────────────────── staff directory order/visibility ──────────────────


async def fetch_department_order(db: AsyncSession) -> list[str]:
    res = await db.execute(
        select(StaffDepartmentOrder.department).order_by(
            StaffDepartmentOrder.sort_order.asc()
        )
    )
    return [row for row in res.scalars().all()]


async def fetch_hidden_user_ids(db: AsyncSession) -> list[uuid.UUID]:
    res = await db.execute(
        select(User.id).where(
            User.deleted_at.is_(None),
            User.staff_hidden.is_(True),
        )
    )
    return [row for row in res.scalars().all()]


async def replace_department_order(
    db: AsyncSession, departments: list[str]
) -> None:
    await db.execute(delete(StaffDepartmentOrder))
    if departments:
        await db.execute(
            pg_insert(StaffDepartmentOrder).values(
                [
                    {"department": dept, "sort_order": idx}
                    for idx, dept in enumerate(departments)
                ]
            )
        )


async def apply_user_sort_orders(
    db: AsyncSession, items: list[tuple[uuid.UUID, int]]
) -> None:
    """Полная замена per-user `staff_sort_order`.

    Семантика — `set`, а не `merge`:
    - пользователям, отсутствующим в ``items``, выставляется ``staff_sort_order=NULL``
      (через единичный UPDATE с исключением `items` по id, чтобы не переписывать
      строки, у которых значение и так станет верным сразу после батч-апдейта);
    - пользователям из ``items`` значение применяется одним батч-UPDATE через
      `CASE WHEN ... END`. Дубликаты ``id`` должны быть отсеяны на роуте.

    Вызывать строго внутри транзакции — функция сама не коммитит.
    """
    mapping: dict[uuid.UUID, int] = {}
    for user_id, sort_order in items:
        mapping[user_id] = sort_order

    reset_stmt = update(User).where(
        User.deleted_at.is_(None),
        User.staff_sort_order.isnot(None),
    )
    if mapping:
        reset_stmt = reset_stmt.where(User.id.notin_(list(mapping.keys())))
    await db.execute(reset_stmt.values(staff_sort_order=None))

    if not mapping:
        return
    await db.execute(
        update(User)
        .where(User.id.in_(list(mapping.keys())), User.deleted_at.is_(None))
        .values(staff_sort_order=case(mapping, value=User.id, else_=None))
    )


async def apply_hidden_user_ids(
    db: AsyncSession, hidden_ids: list[uuid.UUID]
) -> None:
    await db.execute(
        update(User)
        .where(User.deleted_at.is_(None), User.staff_hidden.is_(True))
        .values(staff_hidden=False)
    )
    if hidden_ids:
        await db.execute(
            update(User)
            .where(User.id.in_(hidden_ids), User.deleted_at.is_(None))
            .values(staff_hidden=True)
        )
