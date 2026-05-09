"""Frontmatter, section-path, and ZIP helpers for the KB API."""

from __future__ import annotations

import re
import uuid
import zipfile
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy import text as _sa_text
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.kb import KbArticle, KbSection
from app.models.user import User
from app.services.kb_acl import resolve_article_permission, resolve_section_permission

from ._common import _slugify

logger = get_logger(__name__)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            fm_str = content[3:end].strip()
            body = content[end + 4 :].lstrip("\n")
            try:
                fm = yaml.safe_load(fm_str) or {}
                return fm, body
            except Exception:
                pass
    return {}, content


def _build_frontmatter(
    article: KbArticle,
    section_path: str | None,
    author_name: str | None,
) -> str:
    tags = [t.name for t in (article.tags or [])]
    fm: dict[str, Any] = {
        "title": article.title,
        "tags": tags,
        "status": article.status,
        "created": article.created_at.isoformat(),
        "updated": article.updated_at.isoformat(),
    }
    if section_path:
        fm["section"] = section_path
    if author_name:
        fm["author"] = author_name
    return "---\n" + yaml.dump(fm, allow_unicode=True, default_flow_style=False) + "---\n\n"


async def _get_section_path(db: Any, section_id: uuid.UUID | None) -> str | None:
    if not section_id:
        return None
    sql = _sa_text("""
        WITH RECURSIVE ancestors AS (
            SELECT id, title, parent_id, 0 AS depth
            FROM kb_sections
            WHERE id = :section_id AND deleted_at IS NULL
            UNION ALL
            SELECT s.id, s.title, s.parent_id, a.depth + 1
            FROM kb_sections s
            JOIN ancestors a ON s.id = a.parent_id
            WHERE s.deleted_at IS NULL AND a.depth < 10
        )
        SELECT title FROM ancestors ORDER BY depth DESC
    """)
    result = await db.execute(sql, {"section_id": section_id})
    rows = result.fetchall()
    if not rows:
        return None
    return "/" + "/".join(r[0] for r in rows)


async def _get_or_create_section_by_path(
    db: Any,
    path: str,
    user_id: uuid.UUID,
) -> uuid.UUID | None:
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return None

    await db.execute(
        _sa_text("SELECT pg_advisory_xact_lock(hashtext(:path))"),
        {"path": path},
    )

    slugs = [_slugify(p) for p in parts]
    res = await db.execute(
        select(KbSection).where(KbSection.slug.in_(slugs), KbSection.deleted_at.is_(None))
    )
    existing: dict[str, KbSection] = {s.slug: s for s in res.scalars().all()}

    parent_id: uuid.UUID | None = None
    for part, slug in zip(parts, slugs, strict=False):
        sec = existing.get(slug)
        if not sec:
            sec = KbSection(title=part, slug=slug, parent_id=parent_id, created_by=user_id)
            db.add(sec)
            await db.flush()
            existing[slug] = sec
        parent_id = sec.id
    return parent_id


async def _zip_section(
    zf: zipfile.ZipFile,
    section: KbSection,
    db: Any,
    user: User,
    redis: Any,
    prefix: str,
    depth: int = 0,
) -> None:
    if depth > 20:
        logger.warning("kb.zip.max_depth_reached", section_id=str(section.id))
        return

    folder = prefix + re.sub(r"[/\\]", "_", section.title) + "/"

    arts_res = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.section_id == section.id, KbArticle.deleted_at.is_(None))
    )
    articles = arts_res.scalars().all()
    for article in articles:
        perm = await resolve_article_permission(user, article, db, redis)
        if perm is None and user.role != "admin":
            continue
        author_res = (
            await db.execute(select(User.full_name).where(User.id == article.created_by))
            if article.created_by
            else None
        )
        author_name = author_res.scalar_one_or_none() if author_res else None
        section_path = await _get_section_path(db, article.section_id)
        fm = _build_frontmatter(article, section_path, author_name)
        content = (fm + (article.body or "")).encode("utf-8")
        safe_title = re.sub(r"[^\w\- ]", "", article.title)[:60].strip() or "article"
        zf.writestr(folder + safe_title + ".md", content)

    child_res = await db.execute(
        select(KbSection).where(KbSection.parent_id == section.id).order_by(KbSection.sort_order)
    )
    children = child_res.scalars().all()
    for child in children:
        perm = await resolve_section_permission(user, child, db, redis)
        if perm is None and user.role != "admin":
            continue
        await _zip_section(zf, child, db, user, redis, prefix=folder, depth=depth + 1)
