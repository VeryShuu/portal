"""ARQ задачи для новостей: автопубликация, автоархивация, синхронизация пользователей."""
from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def publish_scheduled_news(ctx: dict) -> int:
    """Публикует новости, у которых publish_at <= NOW() и status='draft'."""
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)
    try:
        now = datetime.now(UTC)
        rows = await conn.fetch(
            """
            UPDATE news
            SET status = 'published',
                published_at = $1,
                updated_at = $1
            WHERE status = 'draft'
              AND publish_at IS NOT NULL
              AND publish_at <= $1
              AND deleted_at IS NULL
            RETURNING id, title, target_departments, target_roles
            """,
            now,
        )
        count = len(rows)
        if count:
            logger.info("news.published_scheduled", count=count)
            for row in rows:
                await _enqueue_news_notifications(
                    ctx,
                    news_id=str(row["id"]),
                    news_title=row["title"],
                    target_departments=row["target_departments"] or [],
                    target_roles=row["target_roles"] or [],
                )
        return count
    finally:
        await conn.close()


async def _enqueue_news_notifications(
    ctx: dict,
    *,
    news_id: str,
    news_title: str,
    target_departments: list,
    target_roles: list,
) -> None:
    """Ставит в очередь ARQ задачи уведомлений (in-app + email) для опубликованной новости."""
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await pool.enqueue_job(
            "app.worker.tasks.notifications.notify_news_published",
            news_id=news_id,
            news_title=news_title,
            target_departments=target_departments or None,
            target_roles=target_roles or None,
        )
        await pool.aclose()

        from app.core.database import AsyncSessionLocal
        from app.api.deps import get_redis as _get_redis
        from redis.asyncio import Redis
        from app.services.notifications import notify_users_news_published
        import uuid as _uuid

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        async with AsyncSessionLocal() as db:
            await notify_users_news_published(
                db, redis,
                news_id=_uuid.UUID(news_id),
                news_title=news_title,
                target_departments=target_departments or None,
                target_roles=target_roles or None,
            )
            await db.commit()
        await redis.aclose()
    except Exception as exc:
        logger.exception(
            "news.notification_enqueue_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            news_id=news_id,
        )


async def archive_expired_news(ctx: dict) -> int:
    """Архивирует новости, у которых archive_at <= NOW() и status='published'."""
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)
    try:
        now = datetime.now(UTC)
        result = await conn.execute(
            """
            UPDATE news
            SET status = 'archived',
                updated_at = $1
            WHERE status = 'published'
              AND archive_at IS NOT NULL
              AND archive_at <= $1
              AND deleted_at IS NULL
            """,
            now,
        )
        count = int(result.split()[-1])
        if count:
            logger.info("news.archived_expired", count=count)
        return count
    finally:
        await conn.close()


async def sync_users_from_keycloak(ctx: dict) -> int:
    """Синхронизирует пользователей из Keycloak Admin API в таблицу users."""
    from app.services import keycloak as kc_service
    from app.core.security import extract_user_data

    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)
    synced = 0

    try:
        page = 0
        while True:
            kc_users = await kc_service.get_admin_users(page=page, size=100)
            if not kc_users:
                break

            now = datetime.now(UTC)
            for ku in kc_users:
                if not ku.get("enabled", True):
                    continue

                claims = {
                    "sub": ku["id"],
                    "email": ku.get("email", ""),
                    "name": f"{ku.get('firstName', '')} {ku.get('lastName', '')}".strip(),
                    "preferred_username": ku.get("username", ""),
                    "department": (ku.get("attributes") or {}).get("department", [None])[0],
                    "job_title": (ku.get("attributes") or {}).get("job_title", [None])[0],
                    "phone": (ku.get("attributes") or {}).get("phone", [None])[0],
                    "realm_access": {"roles": []},
                }
                data = extract_user_data(claims)

                await conn.execute(
                    """
                    INSERT INTO users (keycloak_id, email, full_name, department, position, phone,
                                       role, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (keycloak_id) DO UPDATE
                    SET email = EXCLUDED.email,
                        full_name = EXCLUDED.full_name,
                        department = EXCLUDED.department,
                        position = EXCLUDED.position,
                        phone = EXCLUDED.phone,
                        updated_at = EXCLUDED.updated_at
                    """,
                    data["keycloak_id"],
                    data["email"],
                    data["full_name"],
                    data.get("department"),
                    data.get("position"),
                    data.get("phone"),
                    data["role"],
                    now,
                )
                synced += 1

            if len(kc_users) < 100:
                break
            page += 1

    except Exception as exc:
        logger.exception("users.sync_failed", error=str(exc), error_type=type(exc).__name__)
    finally:
        await conn.close()

    logger.info("users.synced", count=synced)
    return synced
