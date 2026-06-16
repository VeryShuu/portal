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
           AND user_id IS NOT NULL) AS active_users_1h
    """
)

_DAILY_LOGINS_SQL = text(
    """
    SELECT date_trunc('day', created_at)::date AS day,
           count(*) AS count
    FROM audit_log
    WHERE created_at >= :cutoff_14d
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
    WHERE published_at >= :cutoff_14d
      AND status = 'published'
      AND deleted_at IS NULL
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
) -> Row[Any]:
    res = await db.execute(
        _SCALARS_SQL,
        {
            "cutoff_30d": cutoff_30d,
            "cutoff_24h": cutoff_24h,
            "cutoff_1h": cutoff_1h,
        },
    )
    return res.one()


async def fetch_daily_logins(db: AsyncSession, *, cutoff_14d: datetime) -> Sequence[Row[Any]]:
    res = await db.execute(_DAILY_LOGINS_SQL, {"cutoff_14d": cutoff_14d})
    return res.all()


async def fetch_daily_publications(db: AsyncSession, *, cutoff_14d: datetime) -> Sequence[Row[Any]]:
    res = await db.execute(_DAILY_PUBLICATIONS_SQL, {"cutoff_14d": cutoff_14d})
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
