from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import case, func, select, update

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.logging import get_logger
from app.core.security import SESSION_COOKIE_NAME
from app.core.uploads import stream_upload_to_path
from app.models.links import ServiceLink
from app.schemas.links import (
    CreateLinkRequest,
    ReorderLinksRequest,
    ServiceLinkList,
    ServiceLinkPublic,
    UpdateLinkRequest,
)
from app.services.audit import push_audit_event
from app.services.session import get_session

LINK_ICONS_DIR = Path("/data/link_icons")
_ALLOWED_ICON_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/svg+xml",
    "image/x-icon",
    "image/vnd.microsoft.icon",
}
_ICON_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
}
MAX_ICON_SIZE = 2 * 1024 * 1024  # 2 MB

router = APIRouter(prefix="/links", tags=["links"])
logger = get_logger(__name__)


@router.get("", response_model=ServiceLinkList, summary="Список ярлыков")
async def list_links(
    user: CurrentUser,
    db: DbDep,
    category: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    orphaned: bool = Query(default=False),
) -> ServiceLinkList:
    hidden_ids: list[str] = user.preferences.get("hidden_link_ids", [])

    stmt = select(ServiceLink)
    if not include_inactive:
        stmt = stmt.where(ServiceLink.is_active.is_(True))
    if category:
        stmt = stmt.where(ServiceLink.category == category)
    if orphaned and user.role == "admin":
        stmt = stmt.where(ServiceLink.created_by.is_(None))

    stmt = stmt.order_by(ServiceLink.sort_order, ServiceLink.title)
    result = await db.execute(stmt)
    all_links = result.scalars().all()

    items = [lnk for lnk in all_links if str(lnk.id) not in hidden_ids]

    count_stmt = select(func.count()).select_from(ServiceLink)
    if not include_inactive:
        count_stmt = count_stmt.where(ServiceLink.is_active.is_(True))
    if orphaned and user.role == "admin":
        count_stmt = count_stmt.where(ServiceLink.created_by.is_(None))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    return ServiceLinkList(items=items, total=total)


@router.patch(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Изменить порядок ярлыков (admin)",
)
async def reorder_links(
    body: ReorderLinksRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    if not body.items:
        return

    request_ids = {item.id for item in body.items}
    existing_result = await db.execute(
        select(ServiceLink.id).where(ServiceLink.id.in_(list(request_ids)))
    )
    existing_ids = {row[0] for row in existing_result.all()}
    if existing_ids != request_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more links not found",
        )

    when_clauses = [(ServiceLink.id == item.id, item.sort_order) for item in body.items]
    sort_case = case(*when_clauses, else_=ServiceLink.sort_order)

    await db.execute(
        update(ServiceLink)
        .where(ServiceLink.id.in_(list(request_ids)))
        .values(sort_order=sort_case, updated_at=datetime.now(UTC))
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="links.reordered",
        user_id=str(admin.id),
        resource_type="link",
        resource_id=None,
        metadata={"count": len(body.items)},
    )
    logger.info("link.reordered", admin=str(admin.id), count=len(body.items))


@router.get("/{link_id}", response_model=ServiceLinkPublic, summary="Получить ярлык")
async def get_link(link_id: uuid.UUID, user: CurrentUser, db: DbDep) -> ServiceLinkPublic:
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return link


async def _build_sso_url(link_url: str, request: Request, redis: RedisDep) -> str:
    """Строит URL с id_token_hint из сессии пользователя (не отдаётся клиенту напрямую)."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    id_token_hint = ""
    if session_id:
        session_data = await get_session(redis, session_id)
        id_token_hint = (session_data or {}).get("id_token", "")

    if id_token_hint:
        separator = "&" if "?" in link_url else "?"
        return f"{link_url}{separator}{urlencode({'id_token_hint': id_token_hint})}"
    return link_url


@router.get("/{link_id}/sso-redirect", summary="Серверный SSO-редирект для ярлыка")
async def sso_redirect(
    link_id: uuid.UUID,
    _user: CurrentUser,
    db: DbDep,
    request: Request,
    redis: RedisDep,
) -> RedirectResponse:
    """302-редирект на целевой сервис с id_token_hint.

    id_token_hint НЕ возвращается клиенту в теле ответа — только через Location-заголовок
    сервера, что исключает попадание токена в историю браузера портала и JS-память.
    """
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    if not link.supports_sso:
        return RedirectResponse(url=link.url, status_code=302)

    url = await _build_sso_url(link.url, request, redis)
    return RedirectResponse(url=url, status_code=302)


@router.get("/{link_id}/sso-url", summary="SSO URL для ярлыка (устарел, используйте sso-redirect)")
async def get_sso_url(
    link_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    request: Request,
    redis: RedisDep,
) -> dict[str, str]:
    """Оставлен для обратной совместимости. Предпочтительный вариант — sso-redirect."""
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    if not link.supports_sso:
        return {"url": link.url}

    url = await _build_sso_url(link.url, request, redis)
    return {"url": url, "sso": True}  # type: ignore[dict-item]


@router.post(
    "",
    response_model=ServiceLinkPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Создать ярлык (admin)",
)
async def create_link(
    body: CreateLinkRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> ServiceLinkPublic:
    link = ServiceLink(
        title=body.title,
        url=body.url,
        icon_url=body.icon_url,
        description=body.description,
        category=body.category,
        sort_order=body.sort_order,
        supports_sso=body.supports_sso,
        is_active=body.is_active,
        created_by=admin.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    await push_audit_event(
        redis,
        event_type="links.created",
        user_id=str(admin.id),
        resource_type="link",
        resource_id=str(link.id),
    )
    logger.info("link.created", link_id=str(link.id), admin=str(admin.id))
    return link


@router.put("/{link_id}", response_model=ServiceLinkPublic, summary="Обновить ярлык (admin)")
async def update_link(
    link_id: uuid.UUID,
    body: UpdateLinkRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> ServiceLinkPublic:
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    changes = body.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(link, field, value)
    link.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(link)
    await push_audit_event(
        redis,
        event_type="links.updated",
        user_id=str(admin.id),
        resource_type="link",
        resource_id=str(link.id),
        metadata={"fields": sorted(changes.keys())},
    )
    logger.info("link.updated", link_id=str(link.id), admin=str(admin.id))
    return link


@router.delete(
    "/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить ярлык (admin)",
)
async def delete_link(
    link_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    _remove_icon_files(link_id)
    await db.delete(link)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="links.deleted",
        user_id=str(admin.id),
        resource_type="link",
        resource_id=str(link_id),
    )
    logger.info("link.deleted", link_id=str(link_id), admin=str(admin.id))


@router.post(
    "/{link_id}/icon",
    response_model=ServiceLinkPublic,
    summary="Загрузить иконку ярлыка (admin)",
)
async def upload_link_icon(
    link_id: uuid.UUID,
    file: UploadFile,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> ServiceLinkPublic:
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    content_type = file.content_type or ""
    ext = _ICON_CONTENT_TYPE_TO_EXT.get(content_type, "png")

    _remove_icon_files(link_id)

    dest = LINK_ICONS_DIR / f"{link_id}.{ext}"
    await stream_upload_to_path(
        file,
        dest,
        max_size=MAX_ICON_SIZE,
        allowed_mimes=_ALLOWED_ICON_TYPES,
    )

    icon_url = f"/media/link_icons/{link_id}.{ext}"
    await db.execute(
        update(ServiceLink)
        .where(ServiceLink.id == link_id)
        .values(icon_url=icon_url, updated_at=datetime.now(UTC))
    )
    await db.commit()
    await db.refresh(link)
    await push_audit_event(
        redis,
        event_type="links.updated",
        user_id=str(admin.id),
        resource_type="link",
        resource_id=str(link_id),
        metadata={"fields": ["icon_url"]},
    )
    logger.info("link.icon.uploaded", link_id=str(link_id), admin=str(admin.id))
    return link


@router.delete(
    "/{link_id}/icon",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить иконку ярлыка (admin)",
)
async def delete_link_icon(
    link_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    _remove_icon_files(link_id)
    await db.execute(
        update(ServiceLink)
        .where(ServiceLink.id == link_id)
        .values(icon_url=None, updated_at=datetime.now(UTC))
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="links.updated",
        user_id=str(admin.id),
        resource_type="link",
        resource_id=str(link_id),
        metadata={"fields": ["icon_url"]},
    )
    logger.info("link.icon.deleted", link_id=str(link_id), admin=str(admin.id))


def _remove_icon_files(link_id: uuid.UUID) -> None:
    LINK_ICONS_DIR.mkdir(parents=True, exist_ok=True)
    for ext in _ICON_CONTENT_TYPE_TO_EXT.values():
        p = LINK_ICONS_DIR / f"{link_id}.{ext}"
        p.unlink(missing_ok=True)
