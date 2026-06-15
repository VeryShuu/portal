"""ServiceLink CRUD + reorder data-access.

HTTP-agnostic persistence helpers; the API handlers add ACL, audit and the
response serialization on top.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.links import ServiceLink
from app.schemas.links import CreateLinkRequest, LinkReorderItem, UpdateLinkRequest


async def get_link_or_404(db: AsyncSession, link_id: uuid.UUID) -> ServiceLink:
    """Load a link by id or raise 404."""
    result = await db.execute(select(ServiceLink).where(ServiceLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return link


async def create_link(
    db: AsyncSession, body: CreateLinkRequest, created_by: uuid.UUID
) -> ServiceLink:
    """Persist a new link and return the refreshed row."""
    link = ServiceLink(
        title=body.title,
        url=body.url,
        icon_url=body.icon_url,
        description=body.description,
        category=body.category,
        sort_order=body.sort_order,
        supports_sso=body.supports_sso,
        is_active=body.is_active,
        show_on_home=body.show_on_home,
        created_by=created_by,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


async def update_link(db: AsyncSession, link: ServiceLink, body: UpdateLinkRequest) -> list[str]:
    """Apply non-None fields to a link; return the sorted list of changed fields."""
    changes = body.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(link, field, value)
    link.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(link)
    return sorted(changes.keys())


async def delete_link(db: AsyncSession, link: ServiceLink) -> None:
    """Delete a link row."""
    await db.delete(link)
    await db.commit()


async def set_icon_url(db: AsyncSession, link_id: uuid.UUID, icon_url: str | None) -> None:
    """Persist a new ``icon_url`` (or clear it) for a link."""
    await db.execute(
        update(ServiceLink)
        .where(ServiceLink.id == link_id)
        .values(icon_url=icon_url, updated_at=datetime.now(UTC))
    )
    await db.commit()


async def reorder_links(db: AsyncSession, items: list[LinkReorderItem]) -> None:
    """Apply new ``sort_order`` values; raise 404 if any id is unknown."""
    request_ids = {item.id for item in items}
    existing_result = await db.execute(
        select(ServiceLink.id).where(ServiceLink.id.in_(list(request_ids)))
    )
    existing_ids = {row[0] for row in existing_result.all()}
    if existing_ids != request_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more links not found",
        )

    when_clauses = [(ServiceLink.id == item.id, item.sort_order) for item in items]
    sort_case = case(*when_clauses, else_=ServiceLink.sort_order)

    await db.execute(
        update(ServiceLink)
        .where(ServiceLink.id.in_(list(request_ids)))
        .values(sort_order=sort_case, updated_at=datetime.now(UTC))
    )
    await db.commit()
