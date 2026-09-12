"""Назначение методистов (``learning_admins``) — только глобальный админ
портала (§3 ТЗ: «назначается глобальным админом», не сам методист).

Мастер-ключ модуля действует и здесь: выключенный learning → 404.
Все мутации — audit-события; чтение имён/почты — по основному движку
(текущий контур портал, ``users`` доступен штатной роли).
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from app.api.deps import AdminDep, DbDep, RedisDep
from app.api.deps import require_learning_module as _module_gate
from app.models.learning import LearningAdmin
from app.models.user import User
from app.schemas.learning import LearningAdminCreate, LearningAdminOut
from app.services.audit import push_audit_event

router = APIRouter(
    prefix="/learning/admins",
    tags=["learning"],
    dependencies=[Depends(_module_gate)],
)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", summary="Список методистов")
async def list_methodists(_admin: AdminDep, db: DbDep) -> list[LearningAdminOut]:
    rows = (
        await db.execute(
            select(LearningAdmin, User.full_name, User.email)
            .join(User, User.id == LearningAdmin.user_id)
            .order_by(LearningAdmin.added_at)
        )
    ).all()
    return [
        LearningAdminOut(
            user_id=row[0].user_id,
            full_name=row[1],
            email=row[2],
            added_at=row[0].added_at,
        )
        for row in rows
    ]


@router.post("", summary="Назначить методиста", status_code=status.HTTP_201_CREATED)
async def assign_methodist(
    body: LearningAdminCreate,
    request: Request,
    admin: AdminDep,
    redis: RedisDep,
    db: DbDep,
) -> dict[str, Any]:
    user = (
        await db.execute(select(User).where(User.id == body.user_id, User.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")
    db.add(LearningAdmin(user_id=body.user_id, added_by=admin.id))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Уже является методистом"
        ) from exc
    await push_audit_event(
        redis,
        event_type="learning.admin_assigned",
        user_id=str(admin.id),
        resource_type="learning_admin",
        resource_id=str(body.user_id),
        resource_title=user.full_name,
        ip_address=_ip(request),
    )
    return {"ok": True, "user_id": str(body.user_id)}


@router.delete("/{user_id}", summary="Снять методиста")
async def revoke_methodist(
    user_id: uuid.UUID,
    request: Request,
    admin: AdminDep,
    redis: RedisDep,
    db: DbDep,
) -> dict[str, Any]:
    res = await db.execute(sa_delete(LearningAdmin).where(LearningAdmin.user_id == user_id))
    if int(cast(CursorResult, res).rowcount or 0) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Не является методистом")
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.admin_revoked",
        user_id=str(admin.id),
        resource_type="learning_admin",
        resource_id=str(user_id),
        ip_address=_ip(request),
    )
    return {"ok": True}
