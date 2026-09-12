"""Категории курсов (справочник модуля, миграция 109).

Плоский упорядоченный справочник («Инструктажи», «ГО и ЧС», …), управляет
методист. Мутации через admin-роутер с audit-событиями; чтение — на
learning-движке (грант SELECT из миграции 109). Soft-delete: курсы,
ссылающиеся на категорию, отвязываются в той же транзакции (FK SET NULL
срабатывает только при hard delete).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningCourse, LearningCourseCategory


async def list_categories(db: AsyncSession) -> list[tuple[LearningCourseCategory, int]]:
    """Активные категории по порядку + количество активных курсов."""
    cats = (
        (
            await db.execute(
                select(LearningCourseCategory)
                .where(LearningCourseCategory.deleted_at.is_(None))
                .order_by(LearningCourseCategory.sort_order, LearningCourseCategory.title)
            )
        )
        .scalars()
        .all()
    )
    counts: dict[uuid.UUID, int] = {}
    for cat_id, cnt in (
        await db.execute(
            select(LearningCourse.category_id, func.count())
            .where(
                LearningCourse.deleted_at.is_(None),
                LearningCourse.category_id.isnot(None),
            )
            .group_by(LearningCourse.category_id)
        )
    ).all():
        counts[cat_id] = cnt
    return [(c, counts.get(c.id, 0)) for c in cats]


async def _title_taken(db: AsyncSession, title: str, exclude_id: uuid.UUID | None = None) -> bool:
    stmt = select(LearningCourseCategory.id).where(
        LearningCourseCategory.deleted_at.is_(None),
        func.lower(LearningCourseCategory.title) == title.strip().lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(LearningCourseCategory.id != exclude_id)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def create_category(db: AsyncSession, *, title: str) -> LearningCourseCategory:
    if await _title_taken(db, title):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Категория с таким названием уже есть")
    cats = await list_categories(db)
    cat = LearningCourseCategory(title=title.strip(), sort_order=len(cats))
    db.add(cat)
    await db.flush()
    return cat


async def get_category(db: AsyncSession, category_id: uuid.UUID) -> LearningCourseCategory | None:
    return (
        await db.execute(
            select(LearningCourseCategory).where(
                LearningCourseCategory.id == category_id,
                LearningCourseCategory.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def ensure_category_exists(db: AsyncSession, category_id: uuid.UUID) -> None:
    """Валидация ссылки из курса: категория обязана быть активной (422 иначе)."""
    if await get_category(db, category_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Категория не найдена")


async def update_category(
    db: AsyncSession, cat: LearningCourseCategory, *, title: str | None
) -> LearningCourseCategory:
    if title is not None:
        if await _title_taken(db, title, exclude_id=cat.id):
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="Категория с таким названием уже есть"
            )
        cat.title = title.strip()
    cat.updated_at = datetime.now(UTC)
    await db.flush()
    return cat


async def reorder_categories(db: AsyncSession, ordered_ids: list[uuid.UUID]) -> None:
    cats = {
        c.id: c
        for c in (
            await db.execute(
                select(LearningCourseCategory).where(LearningCourseCategory.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    }
    if len(ordered_ids) != len(cats) or any(i not in cats for i in ordered_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Список должен содержать все категории ровно один раз",
        )
    for pos, cid in enumerate(ordered_ids):
        cats[cid].sort_order = pos
    await db.flush()


async def soft_delete_category(db: AsyncSession, cat: LearningCourseCategory) -> None:
    """Soft-delete + отвязка курсов (курсы остаются, но без категории)."""
    cat.deleted_at = datetime.now(UTC)
    cat.updated_at = cat.deleted_at
    await db.execute(
        update(LearningCourse)
        .where(LearningCourse.category_id == cat.id)
        .values(category_id=None, updated_at=datetime.now(UTC))
    )
    await db.flush()
