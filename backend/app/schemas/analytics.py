"""Pydantic response schemas for the analytics dashboard endpoints.

Typed responses give request/response validation, a precise OpenAPI contract
(consumed by the frontend ``types.gen.d.ts``) and remove the hand-written
``row -> dict`` / ``int(...)`` / ``.isoformat()`` mapping from the route layer.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class DailyPoint(BaseModel):
    day: date | None = None
    count: int


class DashboardUsers(BaseModel):
    total: int
    active_30d: int
    active_1h: int
    new_30d: int


class DashboardContent(BaseModel):
    news_published_30d: int
    kb_articles_published_30d: int


class DashboardActivity(BaseModel):
    audit_events_24h: int
    logins_24h: int


class DashboardSeries(BaseModel):
    daily_logins_14d: list[DailyPoint]
    daily_publications_14d: list[DailyPoint]


class DashboardOut(BaseModel):
    generated_at: datetime
    users: DashboardUsers
    content: DashboardContent
    activity: DashboardActivity
    series: DashboardSeries


class TopArticleOut(BaseModel):
    id: uuid.UUID
    title: str
    section_title: str
    view_count: int
    published_at: datetime | None = None
    updated_at: datetime | None = None


class TopNewsOut(BaseModel):
    id: uuid.UUID
    title: str
    view_count: int
    published_at: datetime | None = None


class TopFileOut(BaseModel):
    resource_id: str
    title: str
    downloads: int
    last_download: datetime | None = None


class TopLinkOut(BaseModel):
    resource_id: str
    title: str
    clicks: int
    unique_users: int
    last_click: datetime | None = None


class DepartmentOut(BaseModel):
    department: str | None = None
    total_users: int
    active_users: int
    events: int
