"""Разрешение списка адресатов для уведомлений ERP-импорта.

По умолчанию — все админы (``role='admin'``) с соответствующим consent-флагом:
``notify_email`` для email, ``notify_inapp`` для in-app. Если админ задал
``erp_sync_settings.notify_emails`` (override-список) — используется он
вместо админ-запроса (для email; для in-app всё равно берём всех админов,
т.к. уведомление в колокольчик по конкретным email не имеет смысла).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.erp_sync import ErpSyncSettings
from app.models.user import User

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


async def get_report_emails(db: AsyncSession, settings: ErpSyncSettings) -> list[str]:
    """Email-адреса для отчётного письма.

    Приоритет: явный ``settings.notify_emails`` (если задан и непустой) → иначе
    все админы с ``notify_email=true``.
    """
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
    """ID всех активных админов с ``notify_inapp=true`` (для in-app уведомлений).

    Пагинация не нужна — портальная ~300 сотрудников, админов единицы.
    """
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
