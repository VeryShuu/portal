"""Helpers around the ``user_attribute_mappings.is_full_name_source`` flag.

Single source of truth for the «которым атрибутом Keycloak перезаписывать
``users.full_name``» policy.  Worker (asyncpg), OIDC callback (SQLAlchemy
async) и admin endpoints используют один и тот же помощник, чтобы
правило «при включённом маппинге attr_key=X, full_name = attributes[X]»
не разъехалось между путями.
"""

from __future__ import annotations

from typing import Any

import asyncpg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_attribute_mapping import UserAttributeMapping


async def get_full_name_attr_key_sa(db: AsyncSession) -> str | None:
    """Return ``attr_key`` of the mapping flagged as full-name source, or ``None``."""
    return (
        await db.execute(
            select(UserAttributeMapping.attr_key).where(
                UserAttributeMapping.is_full_name_source.is_(True),
                UserAttributeMapping.enabled.is_(True),
            )
        )
    ).scalar_one_or_none()


async def get_full_name_attr_key_asyncpg(conn: asyncpg.Connection) -> str | None:
    """asyncpg equivalent of :func:`get_full_name_attr_key_sa` for the worker path."""
    value = await conn.fetchval(
        """
        SELECT attr_key FROM user_attribute_mappings
        WHERE is_full_name_source = TRUE AND enabled = TRUE
        LIMIT 1
        """
    )
    return value if isinstance(value, str) else None


def resolve_full_name(default: str, kc_attrs: dict[str, Any], attr_key: str | None) -> str:
    """Return ``kc_attrs[attr_key]`` (stripped) if non-empty string, else ``default``.

    Handles both scalar string values and single-element lists, mirroring how
    Keycloak's flattened attribute dict represents single-valued entries.
    """
    if not attr_key:
        return default
    raw = kc_attrs.get(attr_key)
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped:
            return stripped
    return default
