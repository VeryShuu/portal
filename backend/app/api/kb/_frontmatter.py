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
from app.services.kb_acl import (
    batch_resolve_article_permissions,
    batch_resolve_section_permissions,
)

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
            except Exception as exc:
                logger.warning("kb.import.invalid_yaml_frontmatter", exc_info=exc)
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
    return "---\n" + str(yaml.dump(fm, allow_unicode=True, default_flow_style=False)) + "---\n\n"


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
    return "/" + "/".join(str(r[0]) for r in rows)


async def _get_or_create_section_by_path(
    db: Any,
    path: str,
    user_id: uuid.UUID,
) -> uuid.UUID | None:
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return None

    parent_id: uuid.UUID | None = None
    for part in parts:
        slug = _slugify(part)

        parent_str = str(parent_id) if parent_id else "root"
        await db.execute(
            _sa_text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"{parent_str}/{slug}"},
        )

        res = await db.execute(
            select(KbSection).where(
                KbSection.parent_id == parent_id,
                KbSection.slug == slug,
                KbSection.deleted_at.is_(None),
            )
        )
        sec = res.scalar_one_or_none()
        if not sec:
            sec = KbSection(title=part, slug=slug, parent_id=parent_id, created_by=user_id)
            db.add(sec)
            await db.flush()
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
    current_section_path: str | None = None,
    author_cache: dict[uuid.UUID, str] | None = None,
) -> None:
    if depth > 20:
        logger.warning("kb.zip.max_depth_reached", section_id=str(section.id))
        return

    if author_cache is None:
        author_cache = {}

    if current_section_path is None:
        current_section_path = await _get_section_path(db, section.id)

    folder = prefix + re.sub(r"[/\\]", "_", section.title) + "/"

    arts_res = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.section_id == section.id, KbArticle.deleted_at.is_(None))
    )
    articles = arts_res.scalars().all()

    # Collect author IDs to fetch in bulk
    missing_author_ids = {
        a.created_by for a in articles if a.created_by and a.created_by not in author_cache
    }
    if missing_author_ids:
        users_res = await db.execute(
            select(User.id, User.full_name).where(User.id.in_(missing_author_ids))
        )
        for u_id, full_name in users_res.all():
            author_cache[u_id] = full_name

    article_perms = await batch_resolve_article_permissions(user, list(articles), db, redis)
    for article in articles:
        perm = article_perms.get(article.id)
        if perm is None and user.role != "admin":
            continue

        author_name = author_cache.get(article.created_by) if article.created_by else None
        fm = _build_frontmatter(article, current_section_path, author_name)
        content = (fm + (article.body or "")).encode("utf-8")
        safe_title = re.sub(r"[^\w\- ]", "", article.title)[:60].strip() or "article"
        zf.writestr(folder + safe_title + ".md", content)

    child_res = await db.execute(
        select(KbSection).where(KbSection.parent_id == section.id).order_by(KbSection.sort_order)
    )
    children = child_res.scalars().all()
    child_perms = await batch_resolve_section_permissions(user, list(children), db, redis)
    for child in children:
        perm = child_perms.get(child.id)
        if perm is None and user.role != "admin":
            continue

        child_path = (
            f"{current_section_path}/{child.title}" if current_section_path else f"/{child.title}"
        )
        await _zip_section(
            zf,
            child,
            db,
            user,
            redis,
            prefix=folder,
            depth=depth + 1,
            current_section_path=child_path,
            author_cache=author_cache,
        )
