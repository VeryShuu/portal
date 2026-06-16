"""Analytics dashboard endpoints (admin only).

Aggregations are computed on-demand via SQL. For larger installations these
queries can be backed by materialized views, but on the target scale (~300
concurrent sessions, retention 12 months) on-the-fly aggregation is sufficient.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from app.api.deps import AdminDep, DbDep
from app.schemas.analytics import (
    DailyPoint,
    DashboardActivity,
    DashboardContent,
    DashboardOut,
    DashboardSeries,
    DashboardUsers,
    DepartmentOut,
    FeedbackStatsOut,
    StaleContentItem,
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
async def get_dashboard(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(14, ge=1, le=365),
) -> DashboardOut:
    now = _now()
    cutoff_30d = now - timedelta(days=30)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_1h = now - timedelta(hours=1)
    cutoff_7d = now - timedelta(days=7)
    cutoff_series = now - timedelta(days=days)

    row = await repo.fetch_dashboard_scalars(
        db,
        cutoff_30d=cutoff_30d,
        cutoff_24h=cutoff_24h,
        cutoff_1h=cutoff_1h,
        cutoff_7d=cutoff_7d,
    )

    daily_logins_rows = await repo.fetch_daily_logins(db, cutoff=cutoff_series)
    daily_publications_rows = await repo.fetch_daily_publications(db, cutoff=cutoff_series)
    daily_active_rows = await repo.fetch_daily_active_users(db, cutoff=cutoff_series)
    daily_uploads_rows = await repo.fetch_daily_uploads(db, cutoff=cutoff_series)

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
            wau_7d=int(row.wau_7d),
            mau_30d=int(row.mau_30d),
        ),
        series=DashboardSeries(
            daily_logins_14d=[DailyPoint(day=r[0], count=int(r[1])) for r in daily_logins_rows],
            daily_publications_14d=[
                DailyPoint(day=r[0], count=int(r[1])) for r in daily_publications_rows
            ],
            daily_active_users=[
                DailyPoint(day=r[0], count=int(r[1])) for r in daily_active_rows
            ],
            daily_uploads=[DailyPoint(day=r[0], count=int(r[1])) for r in daily_uploads_rows],
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


@router.get("/stale-content", summary="Застойный контент (0 просмотров / давно не обновлялся)")
async def stale_content(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(90, ge=1, le=3650),
    limit: int = Query(20, ge=1, le=100),
) -> list[StaleContentItem]:
    rows = await repo.fetch_stale_content(db, cutoff=_cutoff(days), limit=limit)
    return [
        StaleContentItem(
            kind=r["kind"],
            id=r["id"],
            title=r["title"],
            view_count=int(r["view_count"] or 0),
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get("/feedback", summary="Статистика обращений (feedback)")
async def feedback_stats(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
) -> FeedbackStatsOut:
    r = await repo.fetch_feedback_stats(db, cutoff=_cutoff(days))
    avg = r["avg_first_response_seconds"]
    return FeedbackStatsOut(
        total=int(r["total"] or 0),
        open=int(r["open"] or 0),
        in_progress=int(r["in_progress"] or 0),
        closed=int(r["closed"] or 0),
        avg_first_response_seconds=float(avg) if avg is not None else None,
    )


@router.get("/resource-trend", summary="Динамика по конкретному ресурсу (ярлык/файл)")
async def resource_trend(
    _admin: AdminDep,
    db: DbDep,
    resource_id: str = Query(..., min_length=1, max_length=200),
    kind: str = Query("link", pattern="^(link|file)$"),
    days: int = Query(30, ge=1, le=365),
) -> list[DailyPoint]:
    rows = await repo.fetch_resource_trend(
        db, resource_id=resource_id, kind=kind, cutoff=_cutoff(days)
    )
    return [DailyPoint(day=r[0], count=int(r[1])) for r in rows]


_EXPORT_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "top-articles": [
        ("title", "Название"),
        ("section_title", "Раздел"),
        ("view_count", "Просмотры"),
        ("updated_at", "Обновлено"),
    ],
    "top-news": [
        ("title", "Название"),
        ("view_count", "Просмотры"),
        ("published_at", "Опубликовано"),
    ],
    "top-files": [
        ("title", "Название"),
        ("downloads", "Скачиваний"),
        ("last_download", "Последнее скачивание"),
    ],
    "top-links": [
        ("title", "Название"),
        ("clicks", "Переходы"),
        ("unique_users", "Уникальных"),
        ("last_click", "Последний переход"),
    ],
    "departments": [
        ("department", "Отдел"),
        ("total_users", "Всего сотрудников"),
        ("active_users", "Активных"),
        ("events", "Событий"),
    ],
    "stale-content": [
        ("kind", "Тип"),
        ("title", "Название"),
        ("view_count", "Просмотры"),
        ("updated_at", "Обновлено"),
    ],
}


async def _export_rows(db: Any, dataset: str, days: int, limit: int) -> list[dict[str, Any]]:
    cutoff = _cutoff(days)
    if dataset == "top-articles":
        rows = await repo.fetch_top_articles(db, cutoff=cutoff, limit=limit)
    elif dataset == "top-news":
        rows = await repo.fetch_top_news(db, cutoff=cutoff, limit=limit)
    elif dataset == "top-files":
        rows = await repo.fetch_top_files(db, cutoff=cutoff, limit=limit)
    elif dataset == "top-links":
        rows = await repo.fetch_top_links(db, cutoff=cutoff, limit=limit)
    elif dataset == "departments":
        rows = await repo.fetch_department_activity(db, cutoff=cutoff)
    elif dataset == "stale-content":
        rows = await repo.fetch_stale_content(db, cutoff=cutoff, limit=limit)
    else:  # pragma: no cover - guarded by route validation
        raise HTTPException(status_code=400, detail="unknown dataset")
    columns = _EXPORT_COLUMNS[dataset]
    out: list[dict[str, Any]] = []
    for r in rows:
        item: dict[str, Any] = {}
        for key, _label in columns:
            val = r[key]
            if isinstance(val, datetime):
                val = val.isoformat()
            item[key] = val
        out.append(item)
    return out


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


@router.get("/export", summary="Экспорт таблицы аналитики (CSV/XLSX)")
async def export_dataset(
    _admin: AdminDep,
    db: DbDep,
    dataset: str = Query(
        ...,
        pattern="^(top-articles|top-news|top-files|top-links|departments|stale-content)$",
    ),
    fmt: str = Query("csv", alias="format", pattern="^(csv|xlsx)$"),
    days: int = Query(30, ge=1, le=3650),
    limit: int = Query(100, ge=1, le=1000),
) -> Response:
    columns = _EXPORT_COLUMNS[dataset]
    rows = await _export_rows(db, dataset, days, limit)
    headers = [label for _key, label in columns]
    keys = [key for key, _label in columns]

    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = dataset[:31]
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([row.get(k) for k in keys])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return StreamingResponse(
            buf,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="analytics-{dataset}.xlsx"'},
        )

    sio = io.StringIO()
    writer = csv.writer(sio)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_cell(row.get(k)) for k in keys])
    data = "\ufeff" + sio.getvalue()
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="analytics-{dataset}.csv"'},
    )
