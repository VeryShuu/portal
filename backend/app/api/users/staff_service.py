"""Staff directory business-logic layer (/users staff-эндпоинты)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import StaffOrderState, StaffOrderUpdate

from . import users_repo


async def apply_staff_order(
    db: AsyncSession, body: StaffOrderUpdate
) -> StaffOrderState:
    seen: set[str] = set()
    unique_departments: list[str] = []
    for dept in body.departments:
        d = (dept or "").strip()
        if not d or d in seen:
            continue
        seen.add(d)
        unique_departments.append(d)

    user_items: list[tuple] = []
    seen_users: set = set()
    for item in body.users:
        if item.id in seen_users:
            continue
        seen_users.add(item.id)
        user_items.append((item.id, item.sort_order))

    hidden_seen: set = set()
    hidden_unique: list = []
    for uid in body.hidden_user_ids:
        if uid in hidden_seen:
            continue
        hidden_seen.add(uid)
        hidden_unique.append(uid)

    try:
        await users_repo.replace_department_order(db, unique_departments)
        await users_repo.apply_user_sort_orders(db, user_items)
        await users_repo.apply_hidden_user_ids(db, hidden_unique)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    departments = await users_repo.fetch_department_order(db)
    hidden = await users_repo.fetch_hidden_user_ids(db)
    return StaffOrderState(departments=departments, hidden_user_ids=hidden)
