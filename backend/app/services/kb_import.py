"""KB import service: single-article ingestion and vault ZIP validation.

Domain logic with no HTTP transport handling; the API handlers own request
parsing, size limits, and the ``ImportReport`` assembly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.sanitize import sanitize_markdown
from app.core.text import slugify as _slugify_common
from app.models.kb import KbArticle, KbArticleTag, KbSection, KbTag
from app.services.kb_acl import require_article_permission, require_section_permission
from app.services.kb_markdown import get_or_create_section_by_path

# Vault archive guards (denial-of-service / zip-bomb protection).
MAX_VAULT_FILES = 1000
VAULT_UNCOMPRESSED_RATIO = 5


async def import_single_article(
    db: Any,
    user: Any,
    redis: Any,
    title: str,
    body: str,
    tags: list[str],
    section_path: str | None,
    strategy: str,
) -> str:
    section_id: uuid.UUID | None = None
    if section_path:
        section_id = await get_or_create_section_by_path(db, section_path, user.id)

    existing_stmt = select(KbArticle).where(
        KbArticle.title == title, KbArticle.deleted_at.is_(None)
    )
    if section_id is not None:
        existing_stmt = existing_stmt.where(KbArticle.section_id == section_id)
    existing_res = await db.execute(existing_stmt)
    existing = existing_res.scalar_one_or_none()

    if existing:
        if strategy == "skip":
            return "skipped"
        elif strategy == "overwrite":
            await require_article_permission(user, existing, "editor", db, redis)
            existing.body = sanitize_markdown(body)
            existing.updated_at = datetime.now(UTC)
            existing.updated_by = user.id
            await db.flush()
            return "updated"
        else:
            title = f"{title} (импорт)"

    if section_id is not None:
        sec_res = await db.execute(
            select(KbSection).where(KbSection.id == section_id, KbSection.deleted_at.is_(None))
        )
        section = sec_res.scalar_one_or_none()
        if section is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        await require_section_permission(user, section, "editor", db, redis)

    article = KbArticle(
        title=title,
        body=sanitize_markdown(body),
        section_id=section_id,
        status="draft",
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(article)
    await db.flush()

    for tag_name in tags[:20]:
        tag_slug = _slugify_common(tag_name, fallback="tag")
        t_res = await db.execute(select(KbTag).where(KbTag.slug == tag_slug))
        tag_obj = t_res.scalar_one_or_none()
        if not tag_obj:
            tag_obj = KbTag(name=tag_name.strip(), slug=tag_slug)
            db.add(tag_obj)
            await db.flush()
        db.add(KbArticleTag(article_id=article.id, tag_id=tag_obj.id))
        await db.flush()

    return "created"


def validate_vault_archive(infolist: Any, max_bytes: int) -> None:
    """Reject archives with too many files or an excessive uncompressed size."""
    # Limit total number of files in archive to prevent denial of service
    if len(infolist) > MAX_VAULT_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archive contains too many files (limit: 1000)",
        )

    # Limit total uncompressed size to prevent zip-bomb / memory exhaustion
    total_uncompressed_size = sum(info.file_size for info in infolist)
    if total_uncompressed_size > max_bytes * VAULT_UNCOMPRESSED_RATIO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uncompressed archive size is too large (zip-bomb protection)",
        )


def collect_vault_md_files(namelist: list[str], errors: list[str]) -> list[str]:
    """Return the safe ``.md`` entries from a ZIP namelist; append rejects to ``errors``."""
    md_files = []
    for name in namelist:
        if not name.endswith(".md"):
            continue
        # Reject absolute paths, path traversal, backslashes
        if name.startswith("/") or ".." in name or "\\" in name:
            errors.append(f"{name}: Invalid path (traversal, absolute or backslashes not allowed)")
            continue
        # Reject special characters in name that might be dangerous
        if any(c in name for c in '\x00\r\n\t*:?|<>""'):
            errors.append(f"{name}: Invalid characters in filename")
            continue
        md_files.append(name)
    return md_files
