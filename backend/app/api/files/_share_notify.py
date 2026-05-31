"""Recipient resolution + in-app/email notifications for file shares.

Default policy (sharing.md §8.4): in-app to all targeted members; email to
members unless the share targets "Все пользователи" (``__all_users__``).
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.system_config import load_system_settings
from app.models.files import FileFolder, FileShare
from app.models.user import User
from app.services.acl_base import SYSTEM_ALL_USERS_SUBJECT_ID
from app.services.email_outbox import KIND_FILE_SHARE, enqueue_outbox_email
from app.services.notifications import create_notification

logger = get_logger(__name__)

_SHARED_WITH_ME_LINK = "/files?tab=shared-with-me"

_PERMISSION_LABELS_RU = {
    "viewer": "просмотр",
    "editor": "редактирование",
}


def _group_path_variants(subject_id: str) -> list[str]:
    variants = {subject_id}
    if subject_id.startswith("/"):
        variants.add(subject_id.lstrip("/"))
    else:
        variants.add("/" + subject_id)
    return list(variants)


async def _resolve_recipients(
    db: AsyncSession,
    share: FileShare,
) -> tuple[list[User], bool]:
    """Return (recipient users, is_all_users)."""
    if share.subject_type == "user":
        res = await db.execute(
            select(User).where(
                or_(
                    User.keycloak_id == share.subject_id,
                    User.id == _safe_uuid(share.subject_id),
                ),
                User.deleted_at.is_(None),
            )
        )
        return list(res.scalars().all()), False

    # group
    if share.subject_id == SYSTEM_ALL_USERS_SUBJECT_ID:
        res = await db.execute(select(User).where(User.deleted_at.is_(None)))
        return list(res.scalars().all()), True

    variants = _group_path_variants(share.subject_id)
    res = await db.execute(
        select(User).where(
            User.keycloak_groups.overlap(variants),
            User.deleted_at.is_(None),
        )
    )
    return list(res.scalars().all()), False


def _safe_uuid(value: str) -> str | None:
    import uuid

    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return None


def _build_email(filename: str, permission: str, shared_by_name: str, link: str) -> tuple[str, str]:
    perm_label = _PERMISSION_LABELS_RU.get(permission, permission)
    text = (
        f"С вами поделились файлом «{filename}» ({perm_label}) от {shared_by_name}.\n"
        f"Открыть: {link}"
    )
    html = (
        f"<p>С вами поделились файлом <b>«{filename}»</b> "
        f"({perm_label}) от {shared_by_name}.</p>"
        f'<p><a href="{link}">Открыть раздел «Доступные мне»</a></p>'
    )
    return html, text


async def notify_file_shared(
    db: AsyncSession,
    redis: Redis,
    *,
    share: FileShare,
    folder: FileFolder,
    shared_by: User,
) -> None:
    """Send in-app + email notifications to a file share's recipients."""
    recipients, is_all_users = await _resolve_recipients(db, share)
    if not recipients:
        return

    shared_by_name = shared_by.full_name or shared_by.email
    title = f"С вами поделились файлом «{share.filename}»"
    perm_label = _PERMISSION_LABELS_RU.get(share.permission, share.permission)
    body = f"{perm_label} · от {shared_by_name}"

    portal_base_url = (load_system_settings().portal_base_url or "").rstrip("/")
    email_link = f"{portal_base_url}{_SHARED_WITH_ME_LINK}" if portal_base_url else _SHARED_WITH_ME_LINK

    publish_callbacks: list[Callable[[], Coroutine[Any, Any, None]]] = []

    for recipient in recipients:
        if recipient.id == shared_by.id:
            continue
        if recipient.notify_inapp:
            publish = await create_notification(
                db,
                redis,
                user_id=recipient.id,
                type="files.file_shared",
                title=title,
                body=body,
                link=_SHARED_WITH_ME_LINK,
            )
            publish_callbacks.append(publish)

        if not is_all_users and recipient.notify_email and recipient.email:
            html, text = _build_email(
                share.filename, share.permission, shared_by_name, email_link
            )
            await enqueue_outbox_email(
                db,
                kind=KIND_FILE_SHARE,
                to_email=recipient.email,
                subject=title,
                body_html=html,
                body_text=text,
                related_resource_type="file",
                related_resource_id=share.id,
                created_by_user_id=shared_by.id,
            )

    await db.commit()
    for publish in publish_callbacks:
        await publish()
