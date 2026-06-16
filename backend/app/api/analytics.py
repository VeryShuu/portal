"""Analytics dashboard endpoints (admin only).

Aggregations are computed on-demand via SQL. For larger installations these
queries can be backed by materialized views, but on the target scale (~300
concurrent sessions, retention 12 months) on-the-fly aggregation is sufficient.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from app.api.deps import AdminDep, DbDep
from app.services import analytics_repo as repo

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _now() -> datetime:
    return datetime.now(tz=UTC)


@router.get("/dashboard", summary="Сводный дашборд (admin)")
async def get_dashboard(_admin: AdminDep, db: DbDep) -> dict:
    now = _now()
    cutoff_30d = now - timedelta(days=30)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_1h = now - timedelta(hours=1)
    cutoff_14d = now - timedelta(days=14)

    row = await repo.fetch_dashboard_scalars(
        db,
        cutoff_30d=cutoff_30d,
        cutoff_24h=cutoff_24h,
        cutoff_1h=cutoff_1h,
    )

    daily_logins_rows = await repo.fetch_daily_logins(db, cutoff_14d=cutoff_14d)
    daily_logins = [
        {"day": r[0].isoformat() if r[0] else None, "count": int(r[1])} for r in daily_logins_rows
    ]

    daily_publications_rows = await repo.fetch_daily_publications(db, cutoff_14d=cutoff_14d)
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
    rows = await repo.fetch_top_articles(db, cutoff=cutoff, limit=limit)
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
    rows = await repo.fetch_top_news(db, cutoff=cutoff, limit=limit)
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
    rows = await repo.fetch_top_files(db, cutoff=cutoff, limit=limit)
    return [
        {
            "resource_id": r["resource_id"],
            "title": r["title"] or "",
            "downloads": int(r["downloads"]),
            "last_download": r["last_download"].isoformat() if r["last_download"] else None,
        }
        for r in rows
    ]


@router.get("/top-links", summary="Топ ярлыков по переходам (audit_log)")
async def top_links(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    cutoff = _now() - timedelta(days=days)
    rows = await repo.fetch_top_links(db, cutoff=cutoff, limit=limit)
    return [
        {
            "resource_id": r["resource_id"],
            "title": r["title"] or "",
            "clicks": int(r["clicks"]),
            "unique_users": int(r["unique_users"]),
            "last_click": r["last_click"].isoformat() if r["last_click"] else None,
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
    rows = await repo.fetch_department_activity(db, cutoff=cutoff)
    return [
        {
            "department": r["department"],
            "total_users": int(r["total_users"]),
            "active_users": int(r["active_users"]),
            "events": int(r["events"]),
        }
        for r in rows
    ]
