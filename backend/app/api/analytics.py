"""Analytics dashboard endpoints (admin only).

Aggregations are computed on-demand via SQL. For larger installations these
queries can be backed by materialized views, but on the target scale (~300
concurrent sessions, retention 12 months) on-the-fly aggregation is sufficient.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from app.api.deps import AdminDep, DbDep
from app.schemas.analytics import (
    DailyPoint,
    DashboardActivity,
    DashboardContent,
    DashboardOut,
    DashboardSeries,
    DashboardUsers,
    DepartmentOut,
    TopArticleOut,
    TopFileOut,
    TopLinkOut,
    TopNewsOut,
)
from app.services import analytics_repo as repo

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _cutoff(days: int) -> datetime:
    return _now() - timedelta(days=days)


@router.get("/dashboard", summary="Сводный дашборд (admin)")
async def get_dashboard(_admin: AdminDep, db: DbDep) -> DashboardOut:
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
    daily_publications_rows = await repo.fetch_daily_publications(db, cutoff_14d=cutoff_14d)

    return DashboardOut(
        generated_at=now,
        users=DashboardUsers(
            total=int(row.total_users),
            active_30d=int(row.active_users_30d),
            active_1h=int(row.active_users_1h),
            new_30d=int(row.new_users_30d),
        ),
        content=DashboardContent(
            news_published_30d=int(row.published_news_30d),
            kb_articles_published_30d=int(row.published_articles_30d),
        ),
        activity=DashboardActivity(
            audit_events_24h=int(row.audit_24h),
            logins_24h=int(row.logins_24h),
        ),
        series=DashboardSeries(
            daily_logins_14d=[DailyPoint(day=r[0], count=int(r[1])) for r in daily_logins_rows],
            daily_publications_14d=[
                DailyPoint(day=r[0], count=int(r[1])) for r in daily_publications_rows
            ],
        ),
    )


@router.get("/top-articles", summary="Топ статей KB по просмотрам")
async def top_articles(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> list[TopArticleOut]:
    rows = await repo.fetch_top_articles(db, cutoff=_cutoff(days), limit=limit)
    return [
        TopArticleOut(
            id=r["id"],
            title=r["title"],
            section_title=r["section_title"],
            view_count=int(r["view_count"] or 0),
            published_at=r["published_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get("/top-news", summary="Топ новостей по просмотрам")
async def top_news(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> list[TopNewsOut]:
    rows = await repo.fetch_top_news(db, cutoff=_cutoff(days), limit=limit)
    return [
        TopNewsOut(
            id=r["id"],
            title=r["title"],
            view_count=int(r["view_count"] or 0),
            published_at=r["published_at"],
        )
        for r in rows
    ]


@router.get("/top-files", summary="Топ файлов по скачиваниям (audit_log)")
async def top_files(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> list[TopFileOut]:
    rows = await repo.fetch_top_files(db, cutoff=_cutoff(days), limit=limit)
    return [
        TopFileOut(
            resource_id=r["resource_id"],
            title=r["title"] or "",
            downloads=int(r["downloads"]),
            last_download=r["last_download"],
        )
        for r in rows
    ]


@router.get("/top-links", summary="Топ ярлыков по переходам (audit_log)")
async def top_links(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> list[TopLinkOut]:
    rows = await repo.fetch_top_links(db, cutoff=_cutoff(days), limit=limit)
    return [
        TopLinkOut(
            resource_id=r["resource_id"],
            title=r["title"] or "",
            clicks=int(r["clicks"]),
            unique_users=int(r["unique_users"]),
            last_click=r["last_click"],
        )
        for r in rows
    ]


@router.get("/departments", summary="Активность по отделам")
async def departments(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
) -> list[DepartmentOut]:
    rows = await repo.fetch_department_activity(db, cutoff=_cutoff(days))
    return [
        DepartmentOut(
            department=r["department"],
            total_users=int(r["total_users"]),
            active_users=int(r["active_users"]),
            events=int(r["events"]),
        )
        for r in rows
    ]
