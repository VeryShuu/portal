"""Analytics dashboard endpoints (admin only).

Aggregations are computed on-demand via SQL. For larger installations these
queries can be backed by materialized views, but on the target scale (~300
concurrent sessions, retention 12 months) on-the-fly aggregation is sufficient.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.api.deps import AdminDep, DbDep

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


@router.get("/dashboard", summary="Сводный дашборд (admin)")
async def get_dashboard(_admin: AdminDep, db: DbDep) -> dict:
    now = _now()
    cutoff_30d = now - timedelta(days=30)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_1h = now - timedelta(hours=1)
    cutoff_14d = now - timedelta(days=14)

    total_users = (await db.execute(text("SELECT count(*) FROM users"))).scalar_one()
    active_users_30d = (
        await db.execute(
            text("SELECT count(*) FROM users WHERE last_login_at >= :c"),
            {"c": cutoff_30d},
        )
    ).scalar_one()
    new_users_30d = (
        await db.execute(
            text("SELECT count(*) FROM users WHERE created_at >= :c"),
            {"c": cutoff_30d},
        )
    ).scalar_one()

    published_news_30d = (
        await db.execute(
            text(
                "SELECT count(*) FROM news "
                "WHERE status='published' AND published_at >= :c "
                "AND deleted_at IS NULL"
            ),
            {"c": cutoff_30d},
        )
    ).scalar_one()
    published_articles_30d = (
        await db.execute(
            text(
                "SELECT count(*) FROM kb_articles "
                "WHERE status='published' AND published_at >= :c "
                "AND deleted_at IS NULL"
            ),
            {"c": cutoff_30d},
        )
    ).scalar_one()

    audit_24h = (
        await db.execute(
            text("SELECT count(*) FROM audit_log WHERE created_at >= :c"),
            {"c": cutoff_24h},
        )
    ).scalar_one()
    logins_24h = (
        await db.execute(
            text(
                "SELECT count(*) FROM audit_log "
                "WHERE created_at >= :c AND event_type IN ('auth.login','local_login')"
            ),
            {"c": cutoff_24h},
        )
    ).scalar_one()

    active_users_1h = (
        await db.execute(
            text(
                "SELECT count(DISTINCT user_id) FROM audit_log "
                "WHERE created_at >= :c AND user_id IS NOT NULL"
            ),
            {"c": cutoff_1h},
        )
    ).scalar_one()

    daily_logins_rows = (
        await db.execute(
            text(
                """
                SELECT date_trunc('day', created_at)::date AS day,
                       count(*) AS count
                FROM audit_log
                WHERE created_at >= :c
                  AND event_type IN ('auth.login','local_login')
                GROUP BY day
                ORDER BY day
                """
            ),
            {"c": cutoff_14d},
        )
    ).all()
    daily_logins = [
        {"day": row[0].isoformat() if row[0] else None, "count": int(row[1])}
        for row in daily_logins_rows
    ]

    daily_publications_rows = (
        await db.execute(
            text(
                """
                SELECT date_trunc('day', published_at)::date AS day,
                       count(*) AS count
                FROM news
                WHERE published_at >= :c AND status='published'
                  AND deleted_at IS NULL
                GROUP BY day
                ORDER BY day
                """
            ),
            {"c": cutoff_14d},
        )
    ).all()
    daily_publications = [
        {"day": row[0].isoformat() if row[0] else None, "count": int(row[1])}
        for row in daily_publications_rows
    ]

    return {
        "generated_at": now.isoformat(),
        "users": {
            "total": int(total_users),
            "active_30d": int(active_users_30d),
            "active_1h": int(active_users_1h),
            "new_30d": int(new_users_30d),
        },
        "content": {
            "news_published_30d": int(published_news_30d),
            "kb_articles_published_30d": int(published_articles_30d),
        },
        "activity": {
            "audit_events_24h": int(audit_24h),
            "logins_24h": int(logins_24h),
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
    ).mappings().all()
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
    ).mappings().all()
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
                                     'photos.photo_purged',
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
    ).mappings().all()
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
    ).mappings().all()
    return [
        {
            "department": r["department"],
            "total_users": int(r["total_users"]),
            "active_users": int(r["active_users"]),
            "events": int(r["events"]),
        }
        for r in rows
    ]
