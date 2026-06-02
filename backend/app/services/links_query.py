"""ServiceLink listing helpers: filter conditions, hidden-id parsing, counting.

Pure query-building / DB-access logic with no HTTP layer; the API handler owns
the response shape and serialization.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.links import ServiceLink


def build_link_conditions(
    *,
    include_inactive: bool,
    category: str | None,
    orphaned: bool,
    is_admin: bool,
) -> list[Any]:
    """Build the SQL filter conditions shared by the listing and count queries."""
    conditions: list[Any] = []
    if not include_inactive:
        conditions.append(ServiceLink.is_active.is_(True))
    if category:
        conditions.append(ServiceLink.category == category)
    if orphaned and is_admin:
        conditions.append(ServiceLink.created_by.is_(None))
    return conditions


def parse_hidden_uuids(hidden_ids: list[str]) -> list[uuid.UUID]:
    """Parse user-preference hidden ids into UUIDs, skipping malformed entries."""
    hidden_uuids: list[uuid.UUID] = []
    for hid in hidden_ids:
        try:
            hidden_uuids.append(uuid.UUID(str(hid)))
        except (ValueError, TypeError):
            continue
    return hidden_uuids


async def list_service_links(
    db: AsyncSession,
    conditions: list[Any],
    hidden_ids: list[str],
) -> tuple[list[ServiceLink], int]:
    """Fetch ordered links (minus hidden ones) plus the total count for the filter."""
    stmt = (
        select(ServiceLink).where(*conditions).order_by(ServiceLink.sort_order, ServiceLink.title)
    )
    result = await db.execute(stmt)
    all_links = result.scalars().all()
    items = [lnk for lnk in all_links if str(lnk.id) not in hidden_ids]

    count_stmt = select(func.count()).select_from(ServiceLink).where(*conditions)
    hidden_uuids = parse_hidden_uuids(hidden_ids)
    if hidden_uuids:
        count_stmt = count_stmt.where(ServiceLink.id.notin_(hidden_uuids))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    return items, total
