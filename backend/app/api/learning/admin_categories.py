"""CRUD справочника категорий курсов (миграция 109) — методист модуля.

Гранулярность как у курсов: ``LearningAdminDep`` + мастер-ключ модуля.
Все мутации — audit-события; удаление — soft (курсы отвязываются,
см. categories_service).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import LearningAdminDep, LearningDbDep, RedisDep
from app.api.deps import require_learning_admin as _admin
from app.schemas.learning import (
    CategoryCreate,
    CategoryOut,
    CategoryReorder,
    CategoryUpdate,
)
from app.services.audit import push_audit_event
from app.services.learning import categories_service as cats_svc


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


router = APIRouter(
    prefix="/learning/admin/categories",
    tags=["learning"],
    dependencies=[Depends(_admin)],
)


@router.get("", summary="Список категорий (по порядку)")
async def list_categories(db: LearningDbDep) -> list[CategoryOut]:
    return [
        CategoryOut(id=c.id, title=c.title, sort_order=c.sort_order, course_count=cnt)
        for c, cnt in await cats_svc.list_categories(db)
    ]


@router.post("", summary="Создать категорию", status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> CategoryOut:
    cat = await cats_svc.create_category(db, title=body.title)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.category_created",
        user_id=str(admin.id),
        resource_type="learning_category",
        resource_id=str(cat.id),
        resource_title=cat.title,
        ip_address=_ip(request),
    )
    return CategoryOut(id=cat.id, title=cat.title, sort_order=cat.sort_order)


@router.patch("/{category_id}", summary="Переименовать категорию")
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> CategoryOut:
    cat = await cats_svc.get_category(db, category_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Категория не найдена")
    await cats_svc.update_category(db, cat, title=body.title)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.category_updated",
        user_id=str(admin.id),
        resource_type="learning_category",
        resource_id=str(cat.id),
        resource_title=cat.title,
        ip_address=_ip(request),
    )
    return CategoryOut(id=cat.id, title=cat.title, sort_order=cat.sort_order)


@router.post("/reorder", summary="Перепорядочить категории")
async def reorder_categories(
    body: CategoryReorder,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    await cats_svc.reorder_categories(db, body.ordered_ids)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.categories_reordered",
        user_id=str(admin.id),
        resource_type="learning_category",
        ip_address=_ip(request),
    )
    return {"ok": True}


@router.delete("/{category_id}", summary="Удалить категорию (soft; курсы отвяжутся)")
async def delete_category(
    category_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    cat = await cats_svc.get_category(db, category_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Категория не найдена")
    await cats_svc.soft_delete_category(db, cat)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.category_deleted",
        user_id=str(admin.id),
        resource_type="learning_category",
        resource_id=str(cat.id),
        resource_title=cat.title,
        ip_address=_ip(request),
    )
    return {"ok": True}
