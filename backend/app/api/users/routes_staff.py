"""Users API: справочник сотрудников (публичный просмотр + админский порядок)."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date

from fastapi import HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.system_config import load_system_settings_shared
from app.schemas.user import (
    DepartmentList,
    OfficeList,
    StaffOrderState,
    StaffOrderUpdate,
    UserList,
    UserPublic,
)
from app.utils.phone import apply_phone_regex

from . import router, users_repo
from .staff_xlsx import export_users_xlsx

_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    if value and value[0] in _CSV_INJECTION_PREFIXES:
        return "'" + value
    return value


@router.get("", response_model=UserList, summary="Список сотрудников")
async def list_users(
    db: DbDep,
    user: CurrentUser,
    q: str | None = Query(default=None, max_length=100),
    department: str | None = Query(default=None),
    office: str | None = Query(default=None),
    sort: str = Query(
        default="full_name", pattern="^(full_name|department|staff_custom)$"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=1000),
    include_hidden: bool = Query(default=False),
) -> UserList:
    if include_hidden and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can request hidden users",
        )
    effective_include_hidden = include_hidden
    if sort != "staff_custom":
        effective_include_hidden = True

    total = await users_repo.count_users(
        db,
        q=q,
        department=department,
        office=office,
        include_hidden=effective_include_hidden,
    )
    items = await users_repo.list_users_page(
        db,
        q=q,
        department=department,
        office=office,
        sort=sort,
        page=page,
        page_size=page_size,
        include_hidden=effective_include_hidden,
    )
    return UserList(
        items=[UserPublic.model_validate(u) for u in items],
        total=total,
    )


@router.get("/departments", response_model=DepartmentList, summary="Список отделов")
async def list_departments_route(
    db: DbDep,
    _: CurrentUser,
    ordered: bool = Query(default=False),
) -> DepartmentList:
    items = await users_repo.list_departments(db, ordered=ordered)
    return DepartmentList(items=items)


@router.get("/offices", response_model=OfficeList, summary="Список офисов")
async def list_offices_route(db: DbDep, _: CurrentUser) -> OfficeList:
    items = await users_repo.list_offices(db)
    return OfficeList(items=items)


@router.get("/export", summary="Экспорт справочника в CSV / XLSX")
async def export_users(
    db: DbDep,
    redis: RedisDep,
    _: CurrentUser,
    q: str | None = Query(default=None, max_length=100),
    department: str | None = Query(default=None),
    office: str | None = Query(default=None),
    sort: str = Query(
        default="department", pattern="^(full_name|department|staff_custom)$"
    ),
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
) -> Response:
    settings = await load_system_settings_shared(redis)
    phone_regex = settings.phone_extract_regex

    if format == "xlsx":
        return await export_users_xlsx(
            db,
            q=q,
            department=department,
            office=office,
            sort=sort,
            phone_regex=phone_regex,
        )

    headers = [
        "full_name",
        "position",
        "department",
        "office",
        "internal_phone",
        "mobile_phone",
        "email",
    ]

    async def generate():
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        yield "\ufeff" + buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        async for user in users_repo.stream_users(
            db,
            q=q,
            department=department,
            office=office,
            sort=sort,
            include_hidden=(sort != "staff_custom"),
        ):
            attrs = user.attributes or {}
            writer.writerow(
                [
                    _csv_safe(user.full_name or ""),
                    _csv_safe(user.position or ""),
                    _csv_safe(user.department or ""),
                    _csv_safe(attrs.get("city", "") or ""),
                    _csv_safe(apply_phone_regex(user.phone or "", phone_regex)),
                    _csv_safe(attrs.get("mobile", "") or ""),
                    _csv_safe(user.email or ""),
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f"staff-{date.today().isoformat()}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, max-age=0",
        },
    )


@router.get(
    "/admin/staff-order",
    response_model=StaffOrderState,
    summary="Текущий порядок отделов и список скрытых пользователей в /staff",
)
async def get_staff_order(db: DbDep, _: AdminDep) -> StaffOrderState:
    departments = await users_repo.fetch_department_order(db)
    hidden = await users_repo.fetch_hidden_user_ids(db)
    return StaffOrderState(departments=departments, hidden_user_ids=hidden)


@router.put(
    "/admin/staff-order",
    response_model=StaffOrderState,
    summary="Сохранить порядок отделов / пользователей и список скрытых",
)
async def put_staff_order(
    body: StaffOrderUpdate,
    admin: AdminDep,
    db: DbDep,
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


@router.get("/{user_id}", response_model=UserPublic, summary="Профиль сотрудника")
async def get_user(
    user_id: uuid.UUID,
    db: DbDep,
    _: CurrentUser,
) -> UserPublic:
    user = await users_repo.fetch_active_user(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserPublic.model_validate(user)
