"""KB расширенные endpoints: ACL, медиа, вложения, экспорт, импорт, diff версий."""
from __future__ import annotations

import difflib
import io
import re
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.sanitize import sanitize_html
from app.core.uploads import stream_upload_to_path
from app.models.kb import (
    KbArticle,
    KbArticleFile,
    KbArticlePermission,
    KbArticleVersion,
    KbSection,
    KbSectionPermission,
)
from app.models.user import User
from app.services.audit import push_audit_event
from app.services import keycloak as kc_service
from app.services.kb_acl import (
    _perm_gte,
    invalidate_article_cache,
    invalidate_section_cache,
    require_article_permission,
    require_section_permission,
    resolve_article_permission,
    resolve_section_permission,
)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])
logger = get_logger(__name__)
settings = get_settings()

KB_MEDIA_DIR = Path("/data/kb/media")
KB_FILES_DIR = Path("/data/kb/files")
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class PermissionEntry(BaseModel):
    id: uuid.UUID
    subject_type: str
    subject_id: str
    subject_name: str
    permission: str
    granted_by: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PermissionList(BaseModel):
    items: list[PermissionEntry]


class SetPermissionRequest(BaseModel):
    subject_type: str = Field(..., pattern="^(user|group)$")
    subject_id: str = Field(min_length=1, max_length=255)
    subject_name: str = Field(min_length=1, max_length=255)
    permission: str = Field(..., pattern="^(viewer|editor|manager)$")


class InheritRequest(BaseModel):
    inherit_permissions: bool


class KbFilePublic(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    original_name: str
    size_bytes: int
    mime_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class KbFileList(BaseModel):
    items: list[KbFilePublic]


class MediaUploadResponse(BaseModel):
    url: str
    filename: str


class UserSearchResult(BaseModel):
    subject_type: str
    subject_id: str
    subject_name: str
    email: str | None = None


class DiffHunk(BaseModel):
    header: str
    lines: list[str]


class DiffResponse(BaseModel):
    hunks: list[DiffHunk]
    stats: dict[str, int]


class ImportReport(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _slugify(text_: str) -> str:
    slug = text_.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return re.sub(r"^-+|-+$", "", slug) or "article"


def _rfc5987_filename(name: str) -> str:
    encoded = quote(name, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            fm_str = content[3:end].strip()
            body = content[end + 4:].lstrip("\n")
            try:
                fm = yaml.safe_load(fm_str) or {}
                return fm, body
            except Exception:
                pass
    return {}, content


def _build_frontmatter(article: KbArticle, section_path: str | None, author_name: str | None) -> str:
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
    result = await db.execute(
        select(KbSection.title, KbSection.parent_id).where(KbSection.id == section_id)
    )
    row = result.fetchone()
    if not row:
        return None
    parts = [row[0]]
    parent_id = row[1]
    depth = 0
    while parent_id and depth < 10:
        r2 = await db.execute(
            select(KbSection.title, KbSection.parent_id).where(KbSection.id == parent_id)
        )
        r = r2.fetchone()
        if not r:
            break
        parts.append(r[0])
        parent_id = r[1]
        depth += 1
    return "/" + "/".join(reversed(parts))


async def _get_or_create_section_by_path(db: Any, path: str, user_id: uuid.UUID) -> uuid.UUID | None:
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return None
    parent_id: uuid.UUID | None = None
    for part in parts:
        slug = _slugify(part)
        res = await db.execute(select(KbSection).where(KbSection.slug == slug))
        sec = res.scalar_one_or_none()
        if not sec:
            sec = KbSection(title=part, slug=slug, parent_id=parent_id, created_by=user_id)
            db.add(sec)
            await db.flush()
        parent_id = sec.id
    return parent_id


# ── Права разделов ────────────────────────────────────────────────────────────

@router.get("/sections/{section_id}/permissions", response_model=PermissionList)
async def get_section_permissions(
    section_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionList:
    sec_res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    section = sec_res.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)
    result = await db.execute(
        select(KbSectionPermission).where(KbSectionPermission.section_id == section_id)
    )
    items = result.scalars().all()
    return PermissionList(items=[PermissionEntry.model_validate(i) for i in items])


@router.post("/sections/{section_id}/permissions", response_model=PermissionEntry, status_code=201)
async def set_section_permission(
    section_id: uuid.UUID,
    body: SetPermissionRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionEntry:
    sec_res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    section = sec_res.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)

    stmt = pg_insert(KbSectionPermission).values(
        section_id=section_id,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        subject_name=body.subject_name,
        permission=body.permission,
        granted_by=user.id,
    ).on_conflict_do_update(
        constraint="uq_kb_sec_perm_section_subject",
        set_={"permission": body.permission, "subject_name": body.subject_name, "granted_by": user.id},
    ).returning(KbSectionPermission)
    result = await db.execute(stmt)
    perm = result.scalar_one()
    await db.commit()
    await invalidate_section_cache(redis, section_id)
    await push_audit_event(
        redis,
        event_type="kb.permission_grant",
        user_id=str(user.id),
        resource_type="kb_section",
        resource_id=str(section_id),
        metadata={
            "subject_id": body.subject_id,
            "subject_type": body.subject_type,
            "permission": body.permission,
        },
    )
    return PermissionEntry.model_validate(perm)


@router.delete("/sections/{section_id}/permissions/{subject_id}", status_code=204)
async def delete_section_permission(
    section_id: uuid.UUID,
    subject_id: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> None:
    sec_res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    section = sec_res.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    await require_section_permission(user, section, "manager", db, redis)
    await db.execute(
        delete(KbSectionPermission).where(
            KbSectionPermission.section_id == section_id,
            KbSectionPermission.subject_id == subject_id,
        )
    )
    await db.commit()
    await invalidate_section_cache(redis, section_id)
    await push_audit_event(
        redis,
        event_type="kb.permission_revoke",
        user_id=str(user.id),
        resource_type="kb_section",
        resource_id=str(section_id),
        metadata={"subject_id": subject_id},
    )


# ── Права статей ──────────────────────────────────────────────────────────────

@router.get("/articles/{article_id}/permissions", response_model=PermissionList)
async def get_article_permissions(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionList:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "manager", db, redis)
    result = await db.execute(
        select(KbArticlePermission).where(KbArticlePermission.article_id == article_id)
    )
    items = result.scalars().all()
    return PermissionList(items=[PermissionEntry.model_validate(i) for i in items])


@router.post("/articles/{article_id}/permissions", response_model=PermissionEntry, status_code=201)
async def set_article_permission(
    article_id: uuid.UUID,
    body: SetPermissionRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> PermissionEntry:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "manager", db, redis)

    stmt = pg_insert(KbArticlePermission).values(
        article_id=article_id,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        subject_name=body.subject_name,
        permission=body.permission,
        granted_by=user.id,
    ).on_conflict_do_update(
        constraint="uq_kb_art_perm_article_subject",
        set_={"permission": body.permission, "subject_name": body.subject_name, "granted_by": user.id},
    ).returning(KbArticlePermission)
    result = await db.execute(stmt)
    perm = result.scalar_one()
    await db.commit()
    await invalidate_article_cache(redis, article_id)
    await push_audit_event(
        redis,
        event_type="kb.permission_grant",
        user_id=str(user.id),
        resource_type="kb_article",
        resource_id=str(article_id),
        metadata={
            "subject_id": body.subject_id,
            "subject_type": body.subject_type,
            "permission": body.permission,
        },
    )
    return PermissionEntry.model_validate(perm)


@router.delete("/articles/{article_id}/permissions/{subject_id}", status_code=204)
async def delete_article_permission(
    article_id: uuid.UUID,
    subject_id: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> None:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "manager", db, redis)
    await db.execute(
        delete(KbArticlePermission).where(
            KbArticlePermission.article_id == article_id,
            KbArticlePermission.subject_id == subject_id,
        )
    )
    await db.commit()
    await invalidate_article_cache(redis, article_id)
    await push_audit_event(
        redis,
        event_type="kb.permission_revoke",
        user_id=str(user.id),
        resource_type="kb_article",
        resource_id=str(article_id),
        metadata={"subject_id": subject_id},
    )


@router.patch("/articles/{article_id}/inherit", response_model=dict)
async def set_inherit_permissions(
    article_id: uuid.UUID,
    body: InheritRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> dict:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "manager", db, redis)

    if not body.inherit_permissions and article.inherit_permissions and article.section_id:
        sec_perms_res = await db.execute(
            select(KbSectionPermission).where(KbSectionPermission.section_id == article.section_id)
        )
        sec_perms = sec_perms_res.scalars().all()
        for sp in sec_perms:
            stmt = pg_insert(KbArticlePermission).values(
                article_id=article_id,
                subject_type=sp.subject_type,
                subject_id=sp.subject_id,
                subject_name=sp.subject_name,
                permission=sp.permission,
                granted_by=user.id,
            ).on_conflict_do_nothing()
            await db.execute(stmt)

    article.inherit_permissions = body.inherit_permissions
    await db.commit()
    await invalidate_article_cache(redis, article_id)
    return {"inherit_permissions": body.inherit_permissions}


# ── Поиск пользователей/групп для picker ──────────────────────────────────────

@router.get("/users/search", response_model=list[UserSearchResult])
async def search_kb_users(
    q: str = Query(min_length=1, max_length=100),
    user: CurrentUser = ...,
    redis: RedisDep = ...,
) -> list[UserSearchResult]:
    if user.role not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        kc_users = await kc_service.search_users(q)
        kc_groups = await kc_service.search_groups(q)
    except Exception as e:
        logger.warning("keycloak.search_failed", error=str(e))
        kc_users, kc_groups = [], []

    results: list[UserSearchResult] = []
    for u in kc_users[:10]:
        results.append(UserSearchResult(
            subject_type="user",
            subject_id=u.get("id", ""),
            subject_name=u.get("firstName", "") + " " + u.get("lastName", ""),
            email=u.get("email"),
        ))
    for g in kc_groups[:10]:
        results.append(UserSearchResult(
            subject_type="group",
            subject_id=g.get("id", ""),
            subject_name=g.get("name", ""),
        ))
    return results


# ── Медиа (изображения в теле статьи) ────────────────────────────────────────

@router.post("/articles/{article_id}/media", response_model=MediaUploadResponse, status_code=201)
async def upload_article_media(
    article_id: uuid.UUID,
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> MediaUploadResponse:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "editor", db, redis)

    safe_name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "image").name)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = KB_MEDIA_DIR / str(article_id) / unique_name

    max_bytes = settings.kb_media_max_size_mb * 1024 * 1024
    await stream_upload_to_path(file, dest, max_size=max_bytes, allowed_mimes=ALLOWED_IMAGE_MIMES)

    url = f"/api/v1/kb/media/{article_id}/{unique_name}"
    return MediaUploadResponse(url=url, filename=unique_name)


@router.get("/media/{article_id}/{filename}")
async def serve_article_media(
    article_id: uuid.UUID,
    filename: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "viewer", db, redis)

    safe = re.sub(r"\.\.", "", filename)
    internal_path = f"/internal/kb-media/{article_id}/{safe}"
    return Response(
        status_code=200,
        headers={"X-Accel-Redirect": internal_path, "Content-Type": ""},
    )


# ── Вложения (файлы к статье) ─────────────────────────────────────────────────

@router.get("/articles/{article_id}/files", response_model=KbFileList)
async def list_article_files(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbFileList:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "viewer", db, redis)

    result = await db.execute(
        select(KbArticleFile)
        .where(KbArticleFile.article_id == article_id)
        .order_by(KbArticleFile.created_at)
    )
    files = result.scalars().all()
    return KbFileList(items=[KbFilePublic.model_validate(f) for f in files])


@router.post("/articles/{article_id}/files", response_model=KbFilePublic, status_code=201)
async def upload_article_file(
    article_id: uuid.UUID,
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbFilePublic:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "editor", db, redis)

    original_name = file.filename or "file"
    safe_stored = f"{uuid.uuid4().hex}_{re.sub(r'[^\\w.\\-]', '_', Path(original_name).name)}"
    dest = KB_FILES_DIR / str(article_id) / safe_stored

    max_bytes = settings.kb_attachment_max_size_mb * 1024 * 1024
    size, mime = await stream_upload_to_path(file, dest, max_size=max_bytes)

    kb_file = KbArticleFile(
        article_id=article_id,
        filename=safe_stored,
        original_name=original_name,
        size_bytes=size,
        mime_type=mime or file.content_type,
        uploaded_by=user.id,
    )
    db.add(kb_file)
    await db.commit()
    await db.refresh(kb_file)
    await push_audit_event(
        redis,
        event_type="kb.file_upload",
        user_id=str(user.id),
        resource_type="kb_article",
        resource_id=str(article_id),
        metadata={"filename": original_name, "size_bytes": size},
    )
    return KbFilePublic.model_validate(kb_file)


@router.delete("/articles/{article_id}/files/{file_id}", status_code=204)
async def delete_article_file(
    article_id: uuid.UUID,
    file_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> None:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    perm = await resolve_article_permission(user, article, db, redis)
    is_uploader_res = await db.execute(
        select(KbArticleFile.uploaded_by).where(KbArticleFile.id == file_id)
    )
    uploader_row = is_uploader_res.fetchone()
    is_owner = uploader_row and uploader_row[0] == user.id

    if not _perm_gte(perm, "editor") and not is_owner and user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    f_res = await db.execute(
        select(KbArticleFile).where(
            KbArticleFile.id == file_id, KbArticleFile.article_id == article_id
        )
    )
    kb_file = f_res.scalar_one_or_none()
    if not kb_file:
        raise HTTPException(status_code=404, detail="File not found")

    disk_path = KB_FILES_DIR / str(article_id) / kb_file.filename
    disk_path.unlink(missing_ok=True)
    await db.delete(kb_file)
    await db.commit()


@router.get("/files/{article_id}/{filename}")
async def download_article_file(
    article_id: uuid.UUID,
    filename: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "viewer", db, redis)

    f_res = await db.execute(
        select(KbArticleFile).where(
            KbArticleFile.article_id == article_id,
            KbArticleFile.filename == filename,
        )
    )
    kb_file = f_res.scalar_one_or_none()
    if not kb_file:
        raise HTTPException(status_code=404, detail="File not found")

    await push_audit_event(
        redis,
        event_type="kb.file_download",
        user_id=str(user.id),
        resource_type="kb_article",
        resource_id=str(article_id),
        metadata={"filename": kb_file.original_name},
    )

    internal_path = f"/internal/kb-files/{article_id}/{filename}"
    cd = _rfc5987_filename(kb_file.original_name)
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": internal_path,
            "Content-Type": kb_file.mime_type or "application/octet-stream",
            "Content-Disposition": cd,
        },
    )


# ── Экспорт ───────────────────────────────────────────────────────────────────

@router.get("/articles/{article_id}/export/md")
async def export_article_md(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    from sqlalchemy.orm import selectinload
    art_res = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "viewer", db, redis)

    author_res = await db.execute(
        select(User.full_name).where(User.id == article.created_by)
    ) if article.created_by else None
    author_name = author_res.scalar_one_or_none() if author_res else None
    section_path = await _get_section_path(db, article.section_id)
    frontmatter = _build_frontmatter(article, section_path, author_name)
    content = frontmatter + (article.body or "")

    safe_title = re.sub(r"[^\w\- ]", "", article.title)[:60].strip() or "article"
    filename = f"{safe_title}.md"
    cd = _rfc5987_filename(filename)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": cd},
    )


@router.get("/sections/{section_id}/export/zip")
async def export_section_zip(
    section_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> StreamingResponse:
    from sqlalchemy.orm import selectinload
    sec_res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    section = sec_res.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    await require_section_permission(user, section, "viewer", db, redis)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        await _zip_section(zf, section, db, user, redis, prefix="")
    buf.seek(0)

    safe_title = re.sub(r"[^\w\- ]", "", section.title)[:40] or "section"
    filename = f"{safe_title}.zip"
    cd = _rfc5987_filename(filename)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/zip",
        headers={"Content-Disposition": cd},
    )


@router.get("/export/vault.zip")
async def export_vault(
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> StreamingResponse:
    from sqlalchemy.orm import selectinload
    sec_res = await db.execute(
        select(KbSection).where(KbSection.parent_id.is_(None)).order_by(KbSection.sort_order)
    )
    root_sections = sec_res.scalars().all()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sec in root_sections:
            perm = await resolve_section_permission(user, sec, db, redis)
            if perm is None and user.role != "admin":
                continue
            await _zip_section(zf, sec, db, user, redis, prefix="")
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=kb-vault.zip"},
    )


async def _zip_section(
    zf: zipfile.ZipFile,
    section: KbSection,
    db: Any,
    user: User,
    redis: Any,
    prefix: str,
) -> None:
    from sqlalchemy.orm import selectinload
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
        author_res = await db.execute(select(User.full_name).where(User.id == article.created_by)) if article.created_by else None
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
        await _zip_section(zf, child, db, user, redis, prefix=folder)


# ── Импорт ────────────────────────────────────────────────────────────────────

@router.post("/articles/import", response_model=ImportReport, status_code=201)
async def import_article_md(
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    strategy: str = Query(default="skip", pattern="^(skip|overwrite|create_new)$"),
) -> ImportReport:
    if user.role not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded")

    fm, body = _parse_frontmatter(content)
    title = fm.get("title") or Path(file.filename or "").stem or "Untitled"
    tags: list[str] = fm.get("tags") or []
    section_path: str | None = fm.get("section")

    section_id: uuid.UUID | None = None
    if section_path:
        section_id = await _get_or_create_section_by_path(db, section_path, user.id)

    slug = _slugify(title)
    existing_res = await db.execute(
        select(KbArticle).where(KbArticle.title == title, KbArticle.deleted_at.is_(None))
    )
    existing = existing_res.scalar_one_or_none()

    if existing:
        if strategy == "skip":
            return ImportReport(created=0, updated=0, skipped=1, errors=[])
        elif strategy == "overwrite":
            existing.body = sanitize_html(body)
            existing.updated_at = datetime.now(timezone.utc)
            existing.updated_by = user.id
            await db.commit()
            return ImportReport(created=0, updated=1, skipped=0, errors=[])
        else:
            title = f"{title} (импорт)"

    from app.models.kb import KbTag, KbArticleTag
    article = KbArticle(
        title=title,
        body=body,
        section_id=section_id,
        status="draft",
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(article)
    await db.flush()

    for tag_name in tags[:20]:
        tag_slug = _slugify(tag_name)
        t_res = await db.execute(select(KbTag).where(KbTag.slug == tag_slug))
        tag = t_res.scalar_one_or_none()
        if not tag:
            tag = KbTag(name=tag_name.strip(), slug=tag_slug)
            db.add(tag)
            await db.flush()
        db.add(KbArticleTag(article_id=article.id, tag_id=tag.id))

    await db.commit()
    return ImportReport(created=1, updated=0, skipped=0, errors=[])


@router.post("/import/vault", response_model=ImportReport, status_code=201)
async def import_vault_zip(
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    strategy: str = Query(default="skip", pattern="^(skip|overwrite|create_new)$"),
) -> ImportReport:
    if user.role not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    content_bytes = await file.read()
    report = ImportReport(created=0, updated=0, skipped=0, errors=[])

    try:
        with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
            md_files = [n for n in zf.namelist() if n.endswith(".md")]
            for md_path in md_files:
                try:
                    raw = zf.read(md_path).decode("utf-8")
                    fm, body = _parse_frontmatter(raw)

                    parts = Path(md_path).parts
                    section_path_from_zip = "/" + "/".join(parts[:-1]) if len(parts) > 1 else None
                    title = fm.get("title") or Path(md_path).stem or "Untitled"
                    tags: list[str] = fm.get("tags") or []
                    section_path = fm.get("section") or section_path_from_zip

                    section_id: uuid.UUID | None = None
                    if section_path:
                        section_id = await _get_or_create_section_by_path(db, section_path, user.id)

                    existing_res = await db.execute(
                        select(KbArticle).where(KbArticle.title == title, KbArticle.deleted_at.is_(None))
                    )
                    existing = existing_res.scalar_one_or_none()

                    if existing:
                        if strategy == "skip":
                            report.skipped += 1
                            continue
                        elif strategy == "overwrite":
                            existing.body = body
                            existing.updated_at = datetime.now(timezone.utc)
                            existing.updated_by = user.id
                            await db.flush()
                            report.updated += 1
                            continue
                        else:
                            title = f"{title} (импорт)"

                    from app.models.kb import KbTag, KbArticleTag
                    article = KbArticle(
                        title=title,
                        body=body,
                        section_id=section_id,
                        status="draft",
                        created_by=user.id,
                        updated_by=user.id,
                    )
                    db.add(article)
                    await db.flush()

                    for tag_name in tags[:20]:
                        tag_slug = _slugify(tag_name)
                        t_res = await db.execute(select(KbTag).where(KbTag.slug == tag_slug))
                        tag_obj = t_res.scalar_one_or_none()
                        if not tag_obj:
                            tag_obj = KbTag(name=tag_name.strip(), slug=tag_slug)
                            db.add(tag_obj)
                            await db.flush()
                        db.add(KbArticleTag(article_id=article.id, tag_id=tag_obj.id))

                    report.created += 1
                except Exception as e:
                    report.errors.append(f"{md_path}: {e}")

        await db.commit()
    except zipfile.BadZipFile:
        raise HTTPException(status_code=422, detail="Invalid ZIP file")

    return report


# ── Diff версий ───────────────────────────────────────────────────────────────

@router.get("/articles/{article_id}/versions/{v1}/diff/{v2}", response_model=DiffResponse)
async def diff_versions(
    article_id: uuid.UUID,
    v1: int,
    v2: int,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> DiffResponse:
    art_res = await db.execute(
        select(KbArticle).where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = art_res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await require_article_permission(user, article, "viewer", db, redis)

    async def _get_body(ver: int) -> str:
        if ver == article.version:
            return article.body or ""
        res = await db.execute(
            select(KbArticleVersion).where(
                KbArticleVersion.article_id == article_id,
                KbArticleVersion.version == ver,
            )
        )
        ver_row = res.scalar_one_or_none()
        if ver_row is None:
            raise HTTPException(status_code=404, detail=f"Version {ver} not found")
        return ver_row.body or ""

    body1 = await _get_body(v1)
    body2 = await _get_body(v2)

    lines1 = body1.splitlines(keepends=True)
    lines2 = body2.splitlines(keepends=True)
    diff = list(difflib.unified_diff(lines1, lines2, fromfile=f"v{v1}", tofile=f"v{v2}", lineterm=""))

    hunks: list[DiffHunk] = []
    current_hunk: DiffHunk | None = None
    added = removed = 0

    for line in diff:
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = DiffHunk(header=line.rstrip(), lines=[])
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif current_hunk is not None:
            current_hunk.lines.append(line.rstrip("\n"))
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1

    if current_hunk:
        hunks.append(current_hunk)

    return DiffResponse(hunks=hunks, stats={"added": added, "removed": removed})
