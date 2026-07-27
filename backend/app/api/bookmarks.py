from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import cast
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.api import bookmarks_repo
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
# Лимит hops редиректов (был max_redirects=3 при follow_redirects=True; после
# перехода на ручной обход с re-валидацией — тот же потолок для UX-консистентности).
_FAVICON_MAX_REDIRECTS = 3
_ALLOWED_FAVICON_CONTENT_TYPES = frozenset(
    {
        "image/x-icon",
        "image/vnd.microsoft.icon",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/svg+xml",
        "image/webp",
        "image/bmp",
    }
)


def _favicon_cache_key(origin: str) -> str:
    h = hashlib.sha256(origin.lower().encode()).hexdigest()[:32]
    return f"favicon:v1:{h}"


async def _do_favicon_fetch(favicon_url: str) -> tuple[int, bytes, str] | None:
    """Безопасный HTTP-запрос за favicon (audit [H1] — SSRF-защита).

    Защиты:
      * **SSRF:** ``follow_redirects=False`` + ручной обход редиректов с
        ре-валидацией каждого hop через ``net_guard.assert_url_safe`` +
        двойной резолв с пиннингом IP (``resolve_stable_ip``) против
        DNS-rebinding. Приватные/loopback/link-local/cloud-metadata адреса
        блокируются. Возвращает ``None`` при небезопасном URL/редиректе.
      * Size-cap и content-type-фильтрация — в caller (``_FAVICON_MAX_SIZE_BYTES``).

    Возвращает ``(status, body, content_type)`` или ``None`` (SSRF-блок).
    Выделена для удобного мокирования в тестах (``_FETCH_PATCH``).
    """
    from app.core.net_guard import assert_url_safe, resolve_stable_ip

    headers = {"User-Agent": "Mozilla/5.0 (compatible; PortalBot/1.0)"}
    try:
        async with httpx.AsyncClient(
            timeout=_FAVICON_FETCH_TIMEOUT,
            follow_redirects=False,
            headers=headers,
        ) as client:
            current = favicon_url
            for _ in range(_FAVICON_MAX_REDIRECTS + 1):
                # Ре-валидация на каждом hop (включая исходный URL): блокируем
                # private/loopback/link-local/cloud-metadata + DNS-rebinding.
                if not await assert_url_safe(current):
                    logger.warning("favicon.ssrf_blocked", url=current)
                    return None
                parsed = urlparse(current)
                host = (parsed.hostname or "").lower()
                if not host or await resolve_stable_ip(host) is None:
                    logger.warning("favicon.dns_rebinding_blocked", url=current)
                    return None
                resp = await client.get(current)
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        return 404, b"", "image/x-icon"
                    current = str(httpx.URL(current).join(location))
                    continue
                break
            else:
                # Цикл завершился без break → превышен лимит редиректов.
                logger.warning("favicon.too_many_redirects", url=favicon_url)
                return 404, b"", "image/x-icon"
    except httpx.RequestError as exc:
        logger.info("favicon.fetch_failed", url=favicon_url, error=str(exc))
        raise

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

    # SSRF-валидация origin только на cache-MISS (audit [H1]): bare-IP из
    # private/loopback/link-local/cloud-metadata и домены, не резолвящиеся в
    # public-IP, блокируются БЕЗ fetch. Negative-cache (TTL 1d) — иначе атакующий
    # мог бы бомбить endpoint разными private-доменами, триггеря sync DNS-resolve
    # в assert_url_safe при каждом запросе (SSRF-amplification / ReDoS-surface).
    # Домены ре-проверяются на SSRF и в fetcher'е — после резолва (защита от
    # DNS-rebinding); здесь — дешёвый early-filter до httpx.
    from app.core.net_guard import assert_url_safe

    if not await assert_url_safe(favicon_url):
        logger.warning("favicon.ssrf_blocked", origin=origin)
        await redis.setex(cache_key, _FAVICON_CACHE_TTL_FAILURE, json.dumps({"ok": False}))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favicon not available")

    try:
        fetch_result = await _do_favicon_fetch(favicon_url)
    except httpx.RequestError as exc:
        await redis.setex(cache_key, _FAVICON_CACHE_TTL_FAILURE, json.dumps({"ok": False}))
        logger.info("favicon.fetch_failed", origin=origin, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Favicon not available"
        ) from exc

    # fetch_result is None → SSRF-блок во время fetch (redirect-to-private,
    # DNS-rebinding). Кэшируем negative-result (TTL 1d) — иначе атакующий мог бы
    # наносить нагрузку повторными запросами, меняя redirect-target.
    if fetch_result is None:
        await redis.setex(cache_key, _FAVICON_CACHE_TTL_FAILURE, json.dumps({"ok": False}))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favicon not available")

    http_status, content, ct = fetch_result
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
    items = await bookmarks_repo.list_user_bookmarks(db, user.id)
    total = await bookmarks_repo.count_user_bookmarks(db, user.id)

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
    user_lock_key = int.from_bytes(hashlib.sha256(user.id.bytes).digest()[:4], "big", signed=True)
    await bookmarks_repo.acquire_user_lock(
        db, namespace=_BOOKMARK_LOCK_NAMESPACE, key=user_lock_key
    )

    count = await bookmarks_repo.count_user_bookmarks(db, user.id)
    if count >= MAX_BOOKMARKS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Maximum {MAX_BOOKMARKS_PER_USER} bookmarks per user",
        )

    next_order = await bookmarks_repo.max_sort_order(db, user.id) + 1

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
    return cast(BookmarkPublic, BookmarkPublic.model_validate(bookmark))


@router.delete("/{bookmark_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить закладку")
async def delete_bookmark(bookmark_id: uuid.UUID, user: CurrentUser, db: DbDep) -> None:
    bookmark = await bookmarks_repo.get_user_bookmark(db, bookmark_id=bookmark_id, user_id=user.id)
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

    user_ids = await bookmarks_repo.list_user_bookmark_ids(db, user.id)

    request_ids = {item.id for item in body.items}
    if not request_ids.issubset(user_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="One or more bookmarks do not belong to you",
        )

    await bookmarks_repo.apply_reorder(
        db,
        user_id=user.id,
        items=[(item.id, item.sort_order) for item in body.items],
    )
    await db.commit()
