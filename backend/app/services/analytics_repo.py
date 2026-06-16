"""Data-access helpers for the analytics dashboard endpoints.

Keeps the (read-only, aggregation-heavy) raw SQL out of the HTTP route
handlers. Response shaping / DTO mapping stays in the route layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Row, RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession

_SCALARS_SQL = text(
    """
    SELECT
        (SELECT count(*) FROM users) AS total_users,
        (SELECT count(*) FROM users WHERE last_login_at >= :cutoff_30d) AS active_users_30d,
        (SELECT count(*) FROM users WHERE created_at >= :cutoff_30d) AS new_users_30d,
        (SELECT count(*) FROM news
         WHERE status = 'published'
           AND published_at >= :cutoff_30d
           AND deleted_at IS NULL) AS published_news_30d,
        (SELECT count(*) FROM kb_articles
         WHERE status = 'published'
           AND published_at >= :cutoff_30d
           AND deleted_at IS NULL) AS published_articles_30d,
        (SELECT count(*) FROM audit_log
         WHERE created_at >= :cutoff_24h) AS audit_24h,
        (SELECT count(*) FROM audit_log
         WHERE created_at >= :cutoff_24h
           AND event_type = 'auth.login') AS logins_24h,
        (SELECT count(DISTINCT user_id) FROM audit_log
         WHERE created_at >= :cutoff_1h
           AND user_id IS NOT NULL) AS active_users_1h,
        (SELECT count(DISTINCT user_id) FROM audit_log
         WHERE created_at >= :cutoff_7d
           AND user_id IS NOT NULL) AS wau_7d,
        (SELECT count(DISTINCT user_id) FROM audit_log
         WHERE created_at >= :cutoff_30d
           AND user_id IS NOT NULL) AS mau_30d
    """
)

_DAILY_LOGINS_SQL = text(
    """
    SELECT date_trunc('day', created_at)::date AS day,
           count(*) AS count
    FROM audit_log
    WHERE created_at >= :cutoff
      AND event_type = 'auth.login'
    GROUP BY day
    ORDER BY day
    """
)

_DAILY_PUBLICATIONS_SQL = text(
    """
    SELECT date_trunc('day', published_at)::date AS day,
           count(*) AS count
    FROM news
    WHERE published_at >= :cutoff
      AND status = 'published'
      AND deleted_at IS NULL
    GROUP BY day
    ORDER BY day
    """
)

_DAILY_ACTIVE_USERS_SQL = text(
    """
    SELECT date_trunc('day', created_at)::date AS day,
           count(DISTINCT user_id) AS count
    FROM audit_log
    WHERE created_at >= :cutoff
      AND user_id IS NOT NULL
    GROUP BY day
    ORDER BY day
    """
)

_DAILY_UPLOADS_SQL = text(
    """
    SELECT date_trunc('day', created_at)::date AS day,
           count(*) AS count
    FROM audit_log
    WHERE created_at >= :cutoff
      AND event_type IN ('files.file_uploaded',
                         'kb.file_upload',
                         'photos.photo_uploaded')
    GROUP BY day
    ORDER BY day
    """
)


async def fetch_dashboard_scalars(
    db: AsyncSession,
    *,
    cutoff_30d: datetime,
    cutoff_24h: datetime,
    cutoff_1h: datetime,
    cutoff_7d: datetime,
) -> Row[Any]:
    res = await db.execute(
        _SCALARS_SQL,
        {
            "cutoff_30d": cutoff_30d,
            "cutoff_24h": cutoff_24h,
            "cutoff_1h": cutoff_1h,
            "cutoff_7d": cutoff_7d,
        },
    )
    return res.one()


async def fetch_daily_logins(db: AsyncSession, *, cutoff: datetime) -> Sequence[Row[Any]]:
    res = await db.execute(_DAILY_LOGINS_SQL, {"cutoff": cutoff})
    return res.all()


async def fetch_daily_publications(db: AsyncSession, *, cutoff: datetime) -> Sequence[Row[Any]]:
    res = await db.execute(_DAILY_PUBLICATIONS_SQL, {"cutoff": cutoff})
    return res.all()


async def fetch_daily_active_users(db: AsyncSession, *, cutoff: datetime) -> Sequence[Row[Any]]:
    res = await db.execute(_DAILY_ACTIVE_USERS_SQL, {"cutoff": cutoff})
    return res.all()


async def fetch_daily_uploads(db: AsyncSession, *, cutoff: datetime) -> Sequence[Row[Any]]:
    res = await db.execute(_DAILY_UPLOADS_SQL, {"cutoff": cutoff})
    return res.all()


async def fetch_top_articles(
    db: AsyncSession, *, cutoff: datetime, limit: int
) -> Sequence[RowMapping]:
    res = await db.execute(
        text(
            """
            SELECT a.id, a.title, a.view_count,
                   COALESCE(s.title, '') AS section_title,
                   a.published_at, a.updated_at
            FROM kb_articles a
            LEFT JOIN kb_sections s ON s.id = a.section_id
            WHERE a.deleted_at IS NULL
              AND a.status='published'
              AND (a.published_at IS NULL OR a.published_at >= :cutoff
                   OR a.updated_at >= :cutoff)
            ORDER BY a.view_count DESC, a.updated_at DESC
            LIMIT :limit
            """
        ),
        {"cutoff": cutoff, "limit": limit},
    )
    return res.mappings().all()


async def fetch_top_news(db: AsyncSession, *, cutoff: datetime, limit: int) -> Sequence[RowMapping]:
    res = await db.execute(
        text(
            """
            SELECT id, title, view_count, published_at
            FROM news
            WHERE deleted_at IS NULL
              AND status='published'
              AND (published_at IS NULL OR published_at >= :cutoff)
            ORDER BY view_count DESC, published_at DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"cutoff": cutoff, "limit": limit},
    )
    return res.mappings().all()


async def fetch_top_files(
    db: AsyncSession, *, cutoff: datetime, limit: int
) -> Sequence[RowMapping]:
    res = await db.execute(
        text(
            """
            SELECT resource_id,
                   COALESCE(
                       NULLIF(MAX(resource_title), ''),
                       MAX(metadata->>'filename')
                   )                   AS title,
                   count(*)            AS downloads,
                   MAX(created_at)     AS last_download
            FROM audit_log
            WHERE created_at >= :cutoff
              AND event_type IN ('files.file_downloaded',
                                 'kb.file_download',
                                 'photos.photo_downloaded',
                                 'kb.article_exported_pdf',
                                 'kb.article_exported_docx')
              AND resource_id IS NOT NULL
            GROUP BY resource_id
            ORDER BY downloads DESC, last_download DESC
            LIMIT :limit
            """
        ),
        {"cutoff": cutoff, "limit": limit},
    )
    return res.mappings().all()


async def fetch_top_links(
    db: AsyncSession, *, cutoff: datetime, limit: int
) -> Sequence[RowMapping]:
    res = await db.execute(
        text(
            """
            SELECT resource_id,
                   MAX(resource_title)             AS title,
                   count(*)                        AS clicks,
                   count(DISTINCT user_id)         AS unique_users,
                   MAX(created_at)                 AS last_click
            FROM audit_log
            WHERE created_at >= :cutoff
              AND event_type = 'links.visited'
              AND resource_id IS NOT NULL
            GROUP BY resource_id
            ORDER BY clicks DESC, last_click DESC
            LIMIT :limit
            """
        ),
        {"cutoff": cutoff, "limit": limit},
    )
    return res.mappings().all()


async def fetch_department_activity(db: AsyncSession, *, cutoff: datetime) -> Sequence[RowMapping]:
    res = await db.execute(
        text(
            """
            SELECT
                COALESCE(NULLIF(u.department, ''), '—') AS department,
                count(DISTINCT u.id)                    AS total_users,
                count(DISTINCT u.id) FILTER (
                    WHERE u.last_login_at >= :cutoff
                ) AS active_users,
                COALESCE(SUM(stats.events), 0)          AS events
            FROM users u
            LEFT JOIN (
                SELECT user_id, count(*) AS events
                FROM audit_log
                WHERE created_at >= :cutoff AND user_id IS NOT NULL
                GROUP BY user_id
            ) stats ON stats.user_id = u.id
            GROUP BY department
            ORDER BY active_users DESC, total_users DESC
            """
        ),
        {"cutoff": cutoff},
    )
    return res.mappings().all()


_DOWNLOAD_EVENTS = (
    "files.file_downloaded",
    "kb.file_download",
    "photos.photo_downloaded",
    "kb.article_exported_pdf",
    "kb.article_exported_docx",
)


async def fetch_stale_content(
    db: AsyncSession, *, cutoff: datetime, limit: int
) -> Sequence[RowMapping]:
    """Опубликованный контент с 0 просмотров ИЛИ не обновлявшийся с ``cutoff``.

    Объединяет статьи KB и новости (поле ``kind``). Сортировка: сначала по числу
    просмотров (ASC), затем по дате обновления (ASC) — наверху самое «застойное».
    """
    res = await db.execute(
        text(
            """
            SELECT kind, id, title, view_count, updated_at FROM (
                SELECT 'kb' AS kind, a.id::text AS id, a.title,
                       COALESCE(a.view_count, 0) AS view_count, a.updated_at
                FROM kb_articles a
                WHERE a.deleted_at IS NULL
                  AND a.status = 'published'
                  AND (COALESCE(a.view_count, 0) = 0 OR a.updated_at < :cutoff)
                UNION ALL
                SELECT 'news' AS kind, n.id::text AS id, n.title,
                       COALESCE(n.view_count, 0) AS view_count, n.updated_at
                FROM news n
                WHERE n.deleted_at IS NULL
                  AND n.status = 'published'
                  AND (COALESCE(n.view_count, 0) = 0 OR n.updated_at < :cutoff)
            ) merged
            ORDER BY view_count ASC, updated_at ASC
            LIMIT :limit
            """
        ),
        {"cutoff": cutoff, "limit": limit},
    )
    return res.mappings().all()


async def fetch_feedback_stats(db: AsyncSession, *, cutoff: datetime) -> RowMapping:
    """Статистика обращений за период: счётчики по статусам + среднее время
    первого ответа (в секундах) для обращений, созданных после ``cutoff``."""
    res = await db.execute(
        text(
            """
            SELECT
                count(*)                                         AS total,
                count(*) FILTER (WHERE f.status = 'open')         AS open,
                count(*) FILTER (WHERE f.status = 'in_progress')  AS in_progress,
                count(*) FILTER (WHERE f.status = 'closed')       AS closed,
                AVG(EXTRACT(EPOCH FROM (fr.first_reply_at - f.created_at)))
                    AS avg_first_response_seconds
            FROM feedback f
            LEFT JOIN (
                SELECT feedback_id, MIN(created_at) AS first_reply_at
                FROM feedback_replies
                GROUP BY feedback_id
            ) fr ON fr.feedback_id = f.id
            WHERE f.created_at >= :cutoff
            """
        ),
        {"cutoff": cutoff},
    )
    return res.mappings().one()


async def fetch_resource_trend(
    db: AsyncSession, *, resource_id: str, kind: str, cutoff: datetime
) -> Sequence[Row[Any]]:
    """Ежедневная динамика событий по конкретному ресурсу.

    ``kind='link'`` → переходы (``links.visited``); ``kind='file'`` → скачивания
    (набор download/export-событий). Фильтр по ``resource_id`` — bind-параметр.
    """
    if kind == "link":
        event_filter = "event_type = 'links.visited'"
        params: dict[str, Any] = {"resource_id": resource_id, "cutoff": cutoff}
    else:
        placeholders = ", ".join(f":ev{i}" for i in range(len(_DOWNLOAD_EVENTS)))
        event_filter = f"event_type IN ({placeholders})"
        params = {"resource_id": resource_id, "cutoff": cutoff}
        for i, ev in enumerate(_DOWNLOAD_EVENTS):
            params[f"ev{i}"] = ev
    res = await db.execute(
        text(
            f"""
            SELECT date_trunc('day', created_at)::date AS day,
                   count(*) AS count
            FROM audit_log
            WHERE created_at >= :cutoff
              AND resource_id = :resource_id
              AND {event_filter}
            GROUP BY day
            ORDER BY day
            """
        ),
        params,
    )
    return res.all()
