from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select, update

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.logging import get_logger
from app.core.security import SESSION_COOKIE_NAME
from app.models.links import ServiceLink
from app.schemas.links import (
    CreateLinkRequest,
    ServiceLinkList,
    ServiceLinkPublic,
    UpdateLinkRequest,
)
from app.services.session import get_session

router = APIRouter(prefix="/links", tags=["links"])
logger = get_logger(__name__)


@router.get("", response_model=ServiceLinkList, summary="Список ярлыков")
async def list_links(
    user: CurrentUser,
    db: DbDep,
    category: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
) -> ServiceLinkList:
    hidden_ids: list[str] = user.preferences.get("hidden_link_ids", [])

    stmt = select(ServiceLink)
    if not include_inactive:
        stmt = stmt.where(ServiceLink.is_active.is_(True))
    if category:
        stmt = stmt.where(ServiceLink.category == category)

    stmt = stmt.order_by(ServiceLink.sort_order, ServiceLink.title)
    result = await db.execute(stmt)
    all_links = result.scalars().all()

    items = [lnk for lnk in all_links if str(lnk.id) not in hidden_ids]

    count_stmt = select(func.count()).select_from(ServiceLink)
    if not include_inactive:
        count_stmt = count_stmt.where(ServiceLink.is_active.is_(True))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    return ServiceLinkList(items=items, total=total)


@router.get("/{link_id}", response_model=ServiceLinkPublic, summary="Получить ярлык")
async def get_link(link_id: uuid.UUID, user: CurrentUser, db: DbDep) -> ServiceLinkPublic:
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return link


@router.get("/{link_id}/sso-url", summary="SSO redirect URL для ярлыка")
async def get_sso_url(
    link_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    request: Request,
    redis: RedisDep,
) -> dict[str, str]:
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    if not link.supports_sso:
        return {"url": link.url}

    id_token_hint = ""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        session_data = await get_session(redis, session_id)
        id_token_hint = (session_data or {}).get("id_token", "")

    if id_token_hint:
        separator = "&" if "?" in link.url else "?"
        url = f"{link.url}{separator}{urlencode({'id_token_hint': id_token_hint})}"
    else:
        url = link.url

    return {"url": url, "sso": True}


@router.post("", response_model=ServiceLinkPublic, status_code=status.HTTP_201_CREATED,
             summary="Создать ярлык (admin)")
async def create_link(body: CreateLinkRequest, admin: AdminDep, db: DbDep) -> ServiceLinkPublic:
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
    logger.info("link.created", link_id=str(link.id), admin=str(admin.id))
    return link


@router.put("/{link_id}", response_model=ServiceLinkPublic, summary="Обновить ярлык (admin)")
async def update_link(
    link_id: uuid.UUID,
    body: UpdateLinkRequest,
    admin: AdminDep,
    db: DbDep,
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
    logger.info("link.updated", link_id=str(link.id), admin=str(admin.id))
    return link


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить ярлык (admin)")
async def delete_link(link_id: uuid.UUID, admin: AdminDep, db: DbDep) -> None:
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    await db.delete(link)
    await db.commit()
    logger.info("link.deleted", link_id=str(link_id), admin=str(admin.id))
