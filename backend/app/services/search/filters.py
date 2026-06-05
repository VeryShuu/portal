"""Search condition/filter builders shared by single- and multi-type queries.

Pure SQLAlchemy predicate construction — no session or HTTP layer. Keeping the
FTS/trgm predicates and per-entity filters here ensures the single-type and the
parallel multi-type branches build identical WHERE clauses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import String, bindparam, or_, text

from app.models.kb import KbArticle
from app.models.links import ServiceLink
from app.models.news import News
from app.models.object_directory import ObjectDirectory, ObjectDirectoryEntry
from app.models.user import User
from app.services.news import news_targeting_conditions

HL_OPTIONS = "MaxWords=20, MinWords=10, StartSel=**, StopSel=**"
DATETIME_MIN_UTC = datetime.min.replace(tzinfo=UTC)


def escape_like(q: str) -> str:
    """Escape LIKE/ILIKE wildcards so user input matches literally."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def article_conditions(
    q: str,
    tsq: Any,
    *,
    from_date: datetime | None,
    to_date: datetime | None,
    author_id: UUID | None,
) -> list[Any]:
    """WHERE conditions for published, accessible KB articles matching ``q``."""
    conditions: list[Any] = [
        KbArticle.deleted_at.is_(None),
        KbArticle.status == "published",
        or_(KbArticle.body_tsvector.op("@@")(tsq), KbArticle.title.op("%")(q)),
    ]
    if from_date:
        conditions.append(KbArticle.created_at >= from_date)
    if to_date:
        conditions.append(KbArticle.created_at <= to_date)
    if author_id:
        conditions.append(KbArticle.created_by == author_id)
    return conditions


def news_conditions(
    q: str,
    tsq: Any,
    user: User,
    *,
    from_date: datetime | None,
    to_date: datetime | None,
    author_id: UUID | None,
    department: str | None,
) -> list[Any]:
    """WHERE conditions for published news matching ``q`` plus role-targeting."""
    conditions: list[Any] = [
        News.deleted_at.is_(None),
        News.status == "published",
        or_(News.body_tsvector.op("@@")(tsq), News.title.op("%")(q)),
    ]
    if user.role not in ("editor", "admin"):
        conditions.extend(news_targeting_conditions(user))
    if from_date:
        conditions.append(News.created_at >= from_date)
    if to_date:
        conditions.append(News.created_at <= to_date)
    if author_id:
        conditions.append(News.author_id == author_id)
    if department:
        conditions.append(
            News.target_departments.op("@>")(
                text("ARRAY[:filter_dept]::varchar[]").bindparams(
                    bindparam("filter_dept", value=department, type_=String)
                )
            )
        )
    return conditions


def link_conditions(q: str) -> list[Any]:
    """WHERE conditions for active service links matching ``q`` (trgm/ILIKE)."""
    q_esc = escape_like(q)
    return [
        ServiceLink.is_active.is_(True),
        or_(
            ServiceLink.title.ilike(f"%{q_esc}%", escape="\\"),
            ServiceLink.description.ilike(f"%{q_esc}%", escape="\\"),
        ),
    ]


def directory_entry_conditions(q: str) -> list[Any]:
    """WHERE conditions for entries (by name) in enabled, non-deleted directories."""
    q_esc = escape_like(q)
    return [
        ObjectDirectoryEntry.deleted_at.is_(None),
        ObjectDirectory.deleted_at.is_(None),
        ObjectDirectory.enabled.is_(True),
        ObjectDirectoryEntry.name.ilike(f"%{q_esc}%", escape="\\"),
    ]


def user_conditions(q: str, *, department: str | None) -> list[Any]:
    """WHERE conditions for users matching ``q`` with optional department filter."""
    q_esc = escape_like(q)
    conditions: list[Any] = [
        or_(
            User.full_name.ilike(f"%{q_esc}%", escape="\\"),
            User.email.ilike(f"%{q_esc}%", escape="\\"),
            User.department.ilike(f"%{q_esc}%", escape="\\"),
            User.position.ilike(f"%{q_esc}%", escape="\\"),
        )
    ]
    if department:
        dept_esc = escape_like(department)
        conditions.append(User.department.ilike(f"%{dept_esc}%", escape="\\"))
    return conditions
