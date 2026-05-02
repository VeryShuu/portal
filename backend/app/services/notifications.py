"""Сервис уведомлений: создание в БД и публикация в Redis Stream."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.notification import Notification
from app.models.user import User

logger = get_logger(__name__)

NOTIFICATIONS_STREAM_KEY = "notifications:{user_id}"


async def create_notification(
    db: AsyncSession,
    redis: Redis,
    *,
    user_id: uuid.UUID,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> Callable[[], Coroutine[Any, Any, None]]:
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        link=link,
    )
    db.add(notif)
    await db.flush()
    await db.refresh(notif)

    async def _publish() -> None:
        await _publish_to_stream(redis, user_id=user_id, notification=notif)

    return _publish


async def _publish_to_stream(
    redis: Redis,
    *,
    user_id: uuid.UUID,
    notification: Notification,
) -> None:
    stream_key = NOTIFICATIONS_STREAM_KEY.format(user_id=str(user_id))
    try:
        payload: dict[str, Any] = {
            "id": str(notification.id),
            "type": notification.type,
            "title": notification.title,
            "body": notification.body or "",
            "link": notification.link or "",
            "created_at": notification.created_at.isoformat(),
        }
        await redis.xadd(stream_key, payload, maxlen=200, approximate=True)  # type: ignore[arg-type]
        await redis.expire(stream_key, 7 * 24 * 3600)
    except Exception as exc:
        logger.exception(
            "notifications.stream_publish_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            user_id=str(user_id),
        )


async def get_unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
    )
    return result.scalar_one()


async def notify_users_news_published(
    db: AsyncSession,
    redis: Redis,
    *,
    news_id: uuid.UUID,
    news_title: str,
    target_departments: list[str] | None = None,
    target_roles: list[str] | None = None,
) -> int:
    """Создаёт уведомления всем целевым пользователям об опубликованной новости.

    Одним SQL-запросом выбирает всех подходящих пользователей (фильтрация
    по отделам/ролям прямо в WHERE), затем пакетно создаёт уведомления.
    """
    from sqlalchemy import and_

    sent = 0
    link = f"/news/{news_id}"
    batch_size = 500
    offset = 0
    publish_callbacks: list[Callable[[], Coroutine[Any, Any, None]]] = []

    conditions = [User.notify_inapp.is_(True)]
    if target_departments:
        conditions.append(User.department.in_(target_departments))
    if target_roles:
        conditions.append(User.role.in_(target_roles))

    while True:
        result = await db.execute(
            select(User).where(and_(*conditions)).order_by(User.id).limit(batch_size).offset(offset)
        )
        users_batch = result.scalars().all()
        if not users_batch:
            break

        for user in users_batch:
            publish = await create_notification(
                db,
                redis,
                user_id=user.id,
                type="news_published",
                title=news_title,
                body=None,
                link=link,
            )
            publish_callbacks.append(publish)
            sent += 1

        if len(users_batch) < batch_size:
            break
        offset += batch_size

    await db.commit()
    for publish in publish_callbacks:
        await publish()

    if sent:
        logger.info("notifications.news_sent", news_id=str(news_id), sent=sent)
    return sent


async def notify_suggestion_reviewed(
    db: AsyncSession,
    redis: Redis,
    *,
    suggestion_author_id: uuid.UUID,
    article_id: uuid.UUID,
    article_title: str,
    action: str,
) -> None:
    """Уведомляет автора правки о решении (approve/reject)."""
    result = await db.execute(
        select(User).where(User.id == suggestion_author_id, User.notify_inapp.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    if action == "approve":
        title = f"Ваша правка к «{article_title}» одобрена"
    else:
        title = f"Ваша правка к «{article_title}» отклонена"

    publish = await create_notification(
        db,
        redis,
        user_id=user.id,
        type="suggestion_reviewed",
        title=title,
        link=f"/kb/articles/{article_id}",
    )
    await db.commit()
    await publish()
