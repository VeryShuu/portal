from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import case, func, select, text
from sqlalchemy import update as sa_update

from app.api.deps import CurrentUser, DbDep
from app.core.logging import get_logger
from app.models.links import Bookmark
from app.schemas.links import (
    BookmarkList,
    BookmarkPublic,
    CreateBookmarkRequest,
    ReorderBookmarksRequest,
)

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])
logger = get_logger(__name__)

MAX_BOOKMARKS_PER_USER = 100

# Advisory-lock namespace для операций над закладками: фиксированный int32 «BOOK».
# pg_advisory_xact_lock(namespace, user_hash) сериализует конкурентные вставки
# в рамках одного user_id и гарантирует соблюдение лимита MAX_BOOKMARKS_PER_USER.
_BOOKMARK_LOCK_NAMESPACE = 0x424F4F4B  # 'BOOK'


@router.get("", response_model=BookmarkList, summary="Список закладок пользователя")
async def list_bookmarks(user: CurrentUser, db: DbDep) -> BookmarkList:
    stmt = (
        select(Bookmark)
        .where(Bookmark.user_id == user.id)
        .order_by(Bookmark.sort_order, Bookmark.created_at)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    count_result = await db.execute(
        select(func.count()).select_from(Bookmark).where(Bookmark.user_id == user.id)
    )
    total = count_result.scalar_one()

    return BookmarkList(items=items, total=total)


@router.post(
    "",
    response_model=BookmarkPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Создать закладку",
)
async def create_bookmark(
    body: CreateBookmarkRequest,
    user: CurrentUser,
    db: DbDep,
) -> BookmarkPublic:
    # Сериализуем конкурентные POST /bookmarks для одного пользователя через
    # pg_advisory_xact_lock — именно это гарантирует лимит и монотонный sort_order.
    user_lock_key = hash(user.id.bytes) & 0x7FFFFFFF
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :k)"),
        {"ns": _BOOKMARK_LOCK_NAMESPACE, "k": user_lock_key},
    )

    count_result = await db.execute(
        select(func.count()).select_from(Bookmark).where(Bookmark.user_id == user.id)
    )
    count = count_result.scalar_one()
    if count >= MAX_BOOKMARKS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {MAX_BOOKMARKS_PER_USER} bookmarks per user",
        )

    max_order_result = await db.execute(
        select(func.coalesce(func.max(Bookmark.sort_order), 0)).where(Bookmark.user_id == user.id)
    )
    next_order = max_order_result.scalar_one() + 1

    bookmark = Bookmark(
        user_id=user.id,
        title=body.title,
        url=body.url,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        group_name=body.group_name,
        sort_order=next_order,
    )
    db.add(bookmark)
    await db.commit()
    await db.refresh(bookmark)
    return bookmark


@router.delete("/{bookmark_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить закладку")
async def delete_bookmark(bookmark_id: uuid.UUID, user: CurrentUser, db: DbDep) -> None:
    result = await db.execute(
        select(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.user_id == user.id)
    )
    bookmark = result.scalar_one_or_none()
    if not bookmark:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bookmark not found")
    await db.delete(bookmark)
    await db.commit()


@router.patch(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Изменить порядок закладок",
)
async def reorder_bookmarks(body: ReorderBookmarksRequest, user: CurrentUser, db: DbDep) -> None:
    if not body.items:
        return

    user_bookmark_ids_result = await db.execute(
        select(Bookmark.id).where(Bookmark.user_id == user.id)
    )
    user_ids = {row[0] for row in user_bookmark_ids_result.all()}

    request_ids = {item.id for item in body.items}
    if not request_ids.issubset(user_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="One or more bookmarks do not belong to you",
        )

    when_clauses = [(Bookmark.id == item.id, item.sort_order) for item in body.items]
    sort_case = case(*when_clauses, else_=Bookmark.sort_order)

    await db.execute(
        sa_update(Bookmark)
        .where(Bookmark.id.in_(list(request_ids)), Bookmark.user_id == user.id)
        .values(sort_order=sort_case)
    )
    await db.commit()
