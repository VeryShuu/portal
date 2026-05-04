"""Analytics dashboard endpoints (admin only).

Aggregations are computed on-demand via SQL. For larger installations these
queries can be backed by materialized views, but on the target scale (~300
concurrent sessions, retention 12 months) on-the-fly aggregation is sufficient.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.api.deps import AdminDep, DbDep

router = APIRouter(prefix="/analytics", tags=["analytics"])

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


def _now() -> datetime:
    return datetime.now(tz=UTC)


@router.get("/dashboard", summary="Сводный дашборд (admin)")
async def get_dashboard(_admin: AdminDep, db: DbDep) -> dict:
    now = _now()
    cutoff_30d = now - timedelta(days=30)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_1h = now - timedelta(hours=1)
    cutoff_14d = now - timedelta(days=14)

    row = (
        await db.execute(
            _SCALARS_SQL,
            {
                "cutoff_30d": cutoff_30d,
                "cutoff_24h": cutoff_24h,
                "cutoff_1h": cutoff_1h,
            },
        )
    ).one()

    daily_logins_rows = (
        await db.execute(_DAILY_LOGINS_SQL, {"cutoff_14d": cutoff_14d})
    ).all()
    daily_logins = [
        {"day": r[0].isoformat() if r[0] else None, "count": int(r[1])}
        for r in daily_logins_rows
    ]

    daily_publications_rows = (
        await db.execute(_DAILY_PUBLICATIONS_SQL, {"cutoff_14d": cutoff_14d})
    ).all()
    daily_publications = [
        {"day": r[0].isoformat() if r[0] else None, "count": int(r[1])}
        for r in daily_publications_rows
    ]

    return {
        "generated_at": now.isoformat(),
        "users": {
            "total": int(row.total_users),
            "active_30d": int(row.active_users_30d),
            "active_1h": int(row.active_users_1h),
            "new_30d": int(row.new_users_30d),
        },
        "content": {
            "news_published_30d": int(row.published_news_30d),
            "kb_articles_published_30d": int(row.published_articles_30d),
        },
        "activity": {
            "audit_events_24h": int(row.audit_24h),
            "logins_24h": int(row.logins_24h),
        },
        "series": {
            "daily_logins_14d": daily_logins,
            "daily_publications_14d": daily_publications,
        },
    }


@router.get("/top-articles", summary="Топ статей KB по просмотрам")
async def top_articles(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    cutoff = _now() - timedelta(days=days)
    rows = (
        (
            await db.execute(
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
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "section_title": r["section_title"],
            "view_count": int(r["view_count"] or 0),
            "published_at": r["published_at"].isoformat() if r["published_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.get("/top-news", summary="Топ новостей по просмотрам")
async def top_news(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    cutoff = _now() - timedelta(days=days)
    rows = (
        (
            await db.execute(
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
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "view_count": int(r["view_count"] or 0),
            "published_at": r["published_at"].isoformat() if r["published_at"] else None,
        }
        for r in rows
    ]


@router.get("/top-files", summary="Топ файлов по скачиваниям (audit_log)")
async def top_files(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    cutoff = _now() - timedelta(days=days)
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT resource_id,
                       MAX(resource_title) AS title,
                       count(*)            AS downloads,
                       MAX(created_at)     AS last_download
                FROM audit_log
                WHERE created_at >= :cutoff
                  AND event_type IN ('files.file_downloaded',
                                     'photos.photo_downloaded',
                                     'kb.article_exported_pdf',
                                     'kb.article_exported_docx',
                                     'news.exported')
                  AND resource_id IS NOT NULL
                GROUP BY resource_id
                ORDER BY downloads DESC
                LIMIT :limit
                """
                ),
                {"cutoff": cutoff, "limit": limit},
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "resource_id": r["resource_id"],
            "title": r["title"] or "",
            "downloads": int(r["downloads"]),
            "last_download": r["last_download"].isoformat() if r["last_download"] else None,
        }
        for r in rows
    ]


@router.get("/departments", summary="Активность по отделам")
async def departments(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
) -> list[dict]:
    cutoff = _now() - timedelta(days=days)
    rows = (
        (
            await db.execute(
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
        )
        .mappings()
        .all()
    )
    return [
        {
            "department": r["department"],
            "total_users": int(r["total_users"]),
            "active_users": int(r["active_users"]),
            "events": int(r["events"]),
        }
        for r in rows
    ]
