from __future__ import annotations

import base64
import hashlib
import json
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import case, func, select, text
from sqlalchemy import update as sa_update

from app.api.deps import CurrentUser, DbDep, RedisDep
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

_FAVICON_CACHE_TTL_SUCCESS = 7 * 24 * 3600  # 7 дней для успешных ответов
_FAVICON_CACHE_TTL_FAILURE = 24 * 3600  # 1 день для ошибок (negative cache)
_FAVICON_MAX_SIZE_BYTES = 500 * 1024  # 500 КБ — разумный лимит для иконок
_FAVICON_FETCH_TIMEOUT = 5.0  # секунд
_ALLOWED_FAVICON_CONTENT_TYPES = frozenset({
    "image/x-icon",
    "image/vnd.microsoft.icon",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/svg+xml",
    "image/webp",
    "image/bmp",
})


def _favicon_cache_key(origin: str) -> str:
    h = hashlib.sha256(origin.lower().encode()).hexdigest()[:32]
    return f"favicon:v1:{h}"


async def _do_favicon_fetch(favicon_url: str) -> tuple[int, bytes, str]:
    """Выполняет HTTP-запрос за favicon. Выделена для удобного мокирования в тестах."""
    async with httpx.AsyncClient(
        timeout=_FAVICON_FETCH_TIMEOUT,
        follow_redirects=True,
        max_redirects=3,
    ) as client:
        resp = await client.get(
            favicon_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; PortalBot/1.0)"},
        )
    ct = resp.headers.get("content-type", "image/x-icon").split(";")[0].strip()
    if ct not in _ALLOWED_FAVICON_CONTENT_TYPES:
        ct = "image/x-icon"
    return resp.status_code, resp.content, ct


@router.get("/favicon", summary="Проксировать favicon сайта (с кэшем 7 дней)")
async def get_bookmark_favicon(
    url: str,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    """Возвращает favicon.ico целевого домена, загруженный на сервере.

    Кэш в Redis: 7 дней для успешных ответов, 1 день для недоступных доменов.
    Endpoint требует аутентификации, но только GET — не требует CSRF-токена.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid URL") from exc

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only http/https URLs are allowed",
        )

    origin = f"{parsed.scheme}://{parsed.netloc}"
    favicon_url = f"{origin}/favicon.ico"
    cache_key = _favicon_cache_key(origin)

    cached_raw = await redis.get(cache_key)
    if cached_raw:
        try:
            cached = json.loads(cached_raw)
            if not cached.get("ok"):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Favicon not available"
                )
            content = base64.b64decode(cached["b64"])
            return Response(content=content, media_type=cached["ct"])
        except (json.JSONDecodeError, KeyError):
            pass

    try:
        http_status, content, ct = await _do_favicon_fetch(favicon_url)
    except httpx.RequestError as exc:
        await redis.setex(cache_key, _FAVICON_CACHE_TTL_FAILURE, json.dumps({"ok": False}))
        logger.info("favicon.fetch_failed", origin=origin, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Favicon not available"
        ) from exc

    if http_status != 200:
        await redis.setex(cache_key, _FAVICON_CACHE_TTL_FAILURE, json.dumps({"ok": False}))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favicon not available")

    if len(content) > _FAVICON_MAX_SIZE_BYTES:
        await redis.setex(cache_key, _FAVICON_CACHE_TTL_FAILURE, json.dumps({"ok": False}))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favicon too large")

    payload = json.dumps({"ok": True, "ct": ct, "b64": base64.b64encode(content).decode()})
    await redis.setex(cache_key, _FAVICON_CACHE_TTL_SUCCESS, payload)

    logger.info("favicon.fetched", origin=origin, content_type=ct, size=len(content))
    return Response(content=content, media_type=ct)


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

    return BookmarkList(
        items=[BookmarkPublic.model_validate(item) for item in items],
        total=total,
    )


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
    # pg_advisory_xact_lock(int4, int4) требует оба аргумента в диапазоне int32.
    user_lock_key = (
        int.from_bytes(hashlib.sha256(user.id.bytes).digest()[:4], "big", signed=True)
    )
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
    return BookmarkPublic.model_validate(bookmark)


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
