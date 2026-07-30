"""Сервис уведомлений: создание в БД и публикация в Redis Stream."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.engine import CursorResult
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
        await redis.xadd(stream_key, payload, maxlen=200, approximate=True)  # type: ignore[arg-type]  # redis-py async-overload typing
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
            select(User.id)
            .where(and_(*conditions))
            .order_by(User.id)
            .limit(batch_size)
            .offset(offset)
        )
        user_ids_batch = result.scalars().all()
        if not user_ids_batch:
            break

        for uid in user_ids_batch:
            publish = await create_notification(
                db,
                redis,
                user_id=uid,
                type="news_published",
                title=news_title,
                body=None,
                link=link,
            )
            publish_callbacks.append(publish)
            sent += 1

        if len(user_ids_batch) < batch_size:
            break
        offset += batch_size

    await db.commit()
    for publish in publish_callbacks:
        await publish()

    if sent:
        logger.info("notifications.news_sent", news_id=str(news_id), sent=sent)
    return sent


_FEEDBACK_CATEGORY_LABELS_RU = {
    "bug": "Ошибка",
    "suggestion": "Предложение",
    "other": "Другое",
}


async def notify_admins_new_feedback(
    db: AsyncSession,
    redis: Redis,
    *,
    feedback_id: uuid.UUID,
    author_id: uuid.UUID | None,
    author_name: str,
    category: str,
) -> int:
    """Уведомить всех админов о новом обращении (кроме самого автора)."""
    sent = 0
    batch_size = 500
    offset = 0
    publish_callbacks: list[Callable[[], Coroutine[Any, Any, None]]] = []

    title = f"Новое обращение от {author_name}"
    body = _FEEDBACK_CATEGORY_LABELS_RU.get(category, category)
    link = "/admin?tab=feedback"

    while True:
        admin_q = (
            select(User.id)
            .where(User.role == "admin", User.notify_inapp.is_(True), User.deleted_at.is_(None))
            .order_by(User.id)
            .limit(batch_size)
            .offset(offset)
        )
        if author_id is not None:
            admin_q = admin_q.where(User.id != author_id)
        result = await db.execute(admin_q)
        user_ids_batch = result.scalars().all()
        if not user_ids_batch:
            break

        for uid in user_ids_batch:
            publish = await create_notification(
                db,
                redis,
                user_id=uid,
                type="feedback_new",
                title=title,
                body=body,
                link=link,
            )
            publish_callbacks.append(publish)
            sent += 1

        if len(user_ids_batch) < batch_size:
            break
        offset += batch_size

    await db.commit()
    for publish in publish_callbacks:
        await publish()

    if sent:
        logger.info(
            "notifications.feedback_new_sent",
            feedback_id=str(feedback_id),
            sent=sent,
        )
    return sent


async def notify_user_feedback_reply(
    db: AsyncSession,
    redis: Redis,
    *,
    feedback_id: uuid.UUID,
    user_id: uuid.UUID,
    admin_name: str,
) -> None:
    """Уведомить автора обращения об ответе администратора."""
    result = await db.execute(
        select(User.id).where(
            User.id == user_id,
            User.notify_inapp.is_(True),
            User.deleted_at.is_(None),
        )
    )
    uid = result.scalar_one_or_none()
    if not uid:
        return

    publish = await create_notification(
        db,
        redis,
        user_id=uid,
        type="feedback_reply",
        title="Администратор ответил на ваше обращение",
        body=f"Ответ от {admin_name}",
        link=f"/my-feedback?open={feedback_id}",
    )
    await db.commit()
    await publish()


async def notify_user_feedback_status_changed(
    db: AsyncSession,
    redis: Redis,
    *,
    feedback_id: uuid.UUID,
    user_id: uuid.UUID,
    new_status: str,
) -> None:
    """Уведомить автора об изменении статуса обращения (только при closed)."""
    if new_status != "closed":
        return

    result = await db.execute(
        select(User.id).where(
            User.id == user_id,
            User.notify_inapp.is_(True),
            User.deleted_at.is_(None),
        )
    )
    uid = result.scalar_one_or_none()
    if not uid:
        return

    publish = await create_notification(
        db,
        redis,
        user_id=uid,
        type="feedback_closed",
        title="Ваше обращение закрыто",
        body=None,
        link=f"/my-feedback?open={feedback_id}",
    )
    await db.commit()
    await publish()


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
        select(User.id).where(User.id == suggestion_author_id, User.notify_inapp.is_(True))
    )
    uid = result.scalar_one_or_none()
    if not uid:
        return

    if action == "approve":
        title = f"Ваша правка к «{article_title}» одобрена"
    else:
        title = f"Ваша правка к «{article_title}» отклонена"

    publish = await create_notification(
        db,
        redis,
        user_id=uid,
        type="suggestion_reviewed",
        title=title,
        link=f"/kb/articles/{article_id}",
    )
    await db.commit()
    await publish()


async def cleanup_old_notifications(
    db: AsyncSession,
    *,
    read_retention_days: int,
    unread_retention_days: int,
) -> dict[str, int]:
    """Удаляет старые уведомления (cron ``notifications.cleanup_notifications``).

    Политика C (как в почтовом клиенте): прочитанные удаляются раньше непрочитанных.
    Каждая ветка отключается значением ``<= 0`` независимо. Два однопроходных
    ``DELETE`` (один на ветку) с bind-параметрами; глобальный скан по
    ``created_at`` использует индекс ``ix_notifications_created_at`` (миграция 085).

    Объём на ~300 пользователей × 90 дней ≈ 270K строк — однопроходный DELETE
    достаточен. При кратном росте таблицы стоит перейти на чанкование по образцу
    ``kb_trash.purge_expired_articles`` (SELECT id LIMIT N → DELETE IN (...) → commit).
    """
    stats = {"read_deleted": 0, "unread_deleted": 0}
    now = datetime.now(UTC)

    if read_retention_days > 0:
        cutoff = now - timedelta(days=read_retention_days)
        res = await db.execute(
            text("DELETE FROM notifications WHERE is_read AND created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        stats["read_deleted"] = int(cast(CursorResult, res).rowcount or 0)

    if unread_retention_days > 0:
        cutoff = now - timedelta(days=unread_retention_days)
        res = await db.execute(
            text("DELETE FROM notifications WHERE NOT is_read AND created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        stats["unread_deleted"] = int(cast(CursorResult, res).rowcount or 0)

    return stats
