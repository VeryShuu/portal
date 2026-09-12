"""Адресаты сводок Directum (клон :mod:`app.services.erp_sync.recipients`).

По умолчанию — все админы с consent-флагами (``notify_email`` / ``notify_inapp``);
явный ``directum_settings.notify_emails`` перекрывает email-список.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.directum import DirectumSettings
from app.models.user import User

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


async def get_report_emails(db: AsyncSession, settings: DirectumSettings) -> list[str]:
    """Email-адреса для сводки прогона: явный override → иначе админы с
    ``notify_email=true``."""
    explicit = settings.notify_emails or []
    if explicit:
        return [e for e in explicit if e]
    res = await db.execute(
        select(User.email).where(
            User.role == "admin",
            User.notify_email.is_(True),
            User.deleted_at.is_(None),
        )
    )
    return list(res.scalars().all())


async def get_admin_user_ids(db: AsyncSession) -> list[uuid.UUID]:
    """ID активных админов с ``notify_inapp=true`` (для watchdog-уведомлений)."""
    res = await db.execute(
        select(User.id)
        .where(
            User.role == "admin",
            User.notify_inapp.is_(True),
            User.deleted_at.is_(None),
        )
        .order_by(User.id)
    )
    return list(res.scalars().all())
