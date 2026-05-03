"""ARQ задачи для новостей: автопубликация, автоархивация, синхронизация пользователей."""

from __future__ import annotations

import contextlib
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
        try:
            await pool.enqueue_job(
                "notify_news_published",
                news_id=news_id,
                news_title=news_title,
                target_departments=target_departments or None,
                target_roles=target_roles or None,
            )
        finally:
            await pool.aclose()

        import uuid as _uuid

        from redis.asyncio import Redis

        from app.core.database import AsyncSessionLocal
        from app.services.notifications import notify_users_news_published

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        async with AsyncSessionLocal() as db:
            await notify_users_news_published(
                db,
                redis,
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


_KC_INTERNAL_ATTR_PREFIXES = ("LDAP_", "KERBEROS_")
_KC_INTERNAL_ATTRS = {"modifyTimestamp", "createTimestamp", "objectClass"}


def _flatten_kc_attributes(raw: dict) -> dict:
    """Convert Keycloak Admin API attributes (dict[str, list[str]]) → dict[str, str | list[str]].

    Drops Keycloak-internal entries (LDAP_*, KERBEROS_*, *Timestamp).
    Single-element lists are unwrapped to scalars; multi-element lists are kept as lists.
    """
    flat: dict = {}
    if not isinstance(raw, dict):
        return flat
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        if key in _KC_INTERNAL_ATTRS or any(key.startswith(p) for p in _KC_INTERNAL_ATTR_PREFIXES):
            continue
        if isinstance(value, list):
            cleaned = [v for v in value if v not in (None, "")]
            if not cleaned:
                continue
            flat[key] = cleaned[0] if len(cleaned) == 1 else cleaned
        elif value not in (None, ""):
            flat[key] = value
    return flat


async def sync_users_from_keycloak(ctx: dict) -> int:
    """Синхронизирует пользователей из Keycloak Admin API в таблицу users."""
    import json as _json

    from redis.asyncio import Redis

    from app.core.security import extract_user_data
    from app.services import keycloak as kc_service

    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)
    synced = 0
    sync_status = "ok"

    seen_kc_ids: set[str] = set()
    disabled_kc_ids: set[str] = set()

    try:
        page = 0
        max_pages = 1000  # safety guard against broken Keycloak pagination
        while page < max_pages:
            kc_users = await kc_service.get_admin_users(page=page, size=100)
            if not kc_users:
                break

            now = datetime.now(UTC)
            for ku in kc_users:
                seen_kc_ids.add(ku["id"])
                if not ku.get("enabled", True):
                    disabled_kc_ids.add(ku["id"])
                    continue

                groups: list[str] = []
                with contextlib.suppress(Exception):
                    groups = await kc_service.get_user_groups(ku["id"])

                raw_attrs = ku.get("attributes") or {}
                flat_attrs = _flatten_kc_attributes(raw_attrs)

                claims = {
                    "sub": ku["id"],
                    "email": ku.get("email", ""),
                    "name": f"{ku.get('firstName', '')} {ku.get('lastName', '')}".strip(),
                    "preferred_username": ku.get("username", ""),
                    "department": flat_attrs.get("department"),
                    "job_title": flat_attrs.get("job_title") or flat_attrs.get("post"),
                    "phone": flat_attrs.get("phone") or flat_attrs.get("telephoneNumber"),
                    "realm_access": {"roles": []},
                    "groups": groups,
                }
                data = extract_user_data(claims)

                await conn.execute(
                    """
                    INSERT INTO users (keycloak_id, email, full_name, department, position, phone,
                                       role, keycloak_groups, attributes, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (keycloak_id) DO UPDATE
                    SET email = EXCLUDED.email,
                        full_name = EXCLUDED.full_name,
                        department = EXCLUDED.department,
                        position = EXCLUDED.position,
                        phone = EXCLUDED.phone,
                        keycloak_groups = EXCLUDED.keycloak_groups,
                        attributes = EXCLUDED.attributes,
                        updated_at = EXCLUDED.updated_at,
                        deleted_at = NULL
                    """,
                    data["keycloak_id"],
                    data["email"],
                    data["full_name"],
                    data.get("department"),
                    data.get("position"),
                    data.get("phone"),
                    data["role"],
                    data.get("keycloak_groups", []),
                    _json.dumps(flat_attrs, ensure_ascii=False),
                    now,
                )
                synced += 1

            if len(kc_users) < 100:
                break
            page += 1

        # Soft-delete users that Keycloak no longer reports as enabled.
        # Выполняем только при успешной полной выборке (sync_status='ok'),
        # иначе при сетевом сбое можно случайно «удалить» полбазы.
        if sync_status == "ok" and seen_kc_ids:
            soft_delete_now = datetime.now(UTC)
            disabled_count = await conn.fetchval(
                """
                WITH upd AS (
                    UPDATE users
                    SET deleted_at = $2, updated_at = $2
                    WHERE auth_source = 'keycloak'
                      AND deleted_at IS NULL
                      AND (
                          keycloak_id = ANY($1::text[])
                          OR (keycloak_id IS NOT NULL
                              AND NOT (keycloak_id = ANY($3::text[])))
                      )
                    RETURNING id
                )
                SELECT count(*) FROM upd
                """,
                list(disabled_kc_ids),
                soft_delete_now,
                list(seen_kc_ids),
            )
            if disabled_count:
                logger.info(
                    "users.sync_soft_deleted",
                    count=int(disabled_count),
                )

    except Exception as exc:
        sync_status = "error"
        logger.exception("users.sync_failed", error=str(exc), error_type=type(exc).__name__)
    finally:
        await conn.close()

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.set(
            "kc:sync_last_run",
            _json.dumps(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "count": synced,
                    "status": sync_status,
                }
            ),
            ex=90 * 24 * 3600,
        )
    finally:
        await redis.aclose()

    logger.info("users.synced", count=synced, status=sync_status)
    return synced
