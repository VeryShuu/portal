"""KB export (MD, ZIP, PDF, DOCX) and import endpoints.

Thin HTTP layer: handlers own ACL checks, audit events, and response shaping;
the heavy lifting lives in ``app.services.kb_export`` / ``kb_import`` / ``kb_markdown``.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.kb import export_import_repo
from app.core.system_config import load_system_settings
from app.schemas.kb_extra import ImportReport
from app.services import kb_export, kb_import
from app.services.audit import make_audit_emitter
from app.services.kb_acl import (
    batch_resolve_section_permissions,
    require_article_permission,
    require_section_permission,
    resolve_article_permission,
)
from app.services.kb_import import import_single_article as _import_single_article
from app.services.kb_markdown import build_frontmatter as _build_frontmatter
from app.services.kb_markdown import get_section_path as _get_section_path
from app.services.kb_markdown import parse_frontmatter as _parse_frontmatter
from app.services.kb_markdown import zip_section as _zip_section

from ._common import _get_article_or_404, _rfc5987_filename
from ._docx_export import render_article_docx
from ._pdf_export import render_article_html_for_pdf

_emit_audit = make_audit_emitter("kb_article")

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


def _kb_import_max_bytes() -> int:
    return load_system_settings().kb_import_max_size_mb * 1024 * 1024


@router.get("/articles/{article_id}/export/md")
async def export_article_md(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    author_name = (
        await export_import_repo.get_author_name(db, article.created_by)
        if article.created_by
        else None
    )
    section_path = await _get_section_path(db, article.section_id)
    frontmatter = _build_frontmatter(article, section_path, author_name)
    content = frontmatter + (article.body or "")

    filename = f"{kb_export.article_md_stem(article.title)}.md"
    cd = _rfc5987_filename(filename)
    await _emit_audit(
        redis,
        event_type="kb.article_exported_md",
        user_id=str(user.id),
        user_email=user.email,
        resource_id=str(article_id),
    )
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
    section = await export_import_repo.get_section(db, section_id)
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    await require_section_permission(user, section, "viewer", db, redis)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        await _zip_section(zf, section, db, user, redis, prefix="")
    buf.seek(0)

    filename = f"{kb_export.section_zip_stem(section.title)}.zip"
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
    root_sections = await export_import_repo.list_root_sections(db)

    root_perms = await batch_resolve_section_permissions(user, list(root_sections), db, redis)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sec in root_sections:
            perm = root_perms.get(sec.id)
            if perm is None and user.role != "admin":
                continue
            await _zip_section(zf, sec, db, user, redis, prefix="")
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=kb-vault.zip"},
    )


@router.post("/articles/import", response_model=ImportReport, status_code=201)
async def import_article_md(
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    strategy: str = Query(default="skip", pattern="^(skip|overwrite|create_new)$"),
) -> ImportReport:
    _kb_import_max_mb = load_system_settings().kb_import_max_size_mb
    max_bytes = _kb_import_max_mb * 1024 * 1024

    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large (max {_kb_import_max_mb} MB)",
        )

    content_bytes = await file.read(max_bytes + 1)
    if len(content_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large (max {_kb_import_max_mb} MB)",
        )
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="File must be UTF-8 encoded"
        ) from exc

    fm, body = _parse_frontmatter(content)
    _stem = Path(file.filename).stem if file.filename else None
    title = fm.get("title") or _stem or "Untitled"
    tags: list[str] = fm.get("tags") or []
    section_path: str | None = fm.get("section")

    outcome = await _import_single_article(
        db, user, redis, title, body, tags, section_path, strategy
    )
    await db.commit()

    if outcome == "skipped":
        return ImportReport(created=0, updated=0, skipped=1, errors=[])
    elif outcome == "updated":
        return ImportReport(created=0, updated=1, skipped=0, errors=[])
    else:
        return ImportReport(created=1, updated=0, skipped=0, errors=[])


@router.post("/import/vault", response_model=ImportReport, status_code=201)
async def import_vault_zip(
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    strategy: str = Query(default="skip", pattern="^(skip|overwrite|create_new)$"),
) -> ImportReport:
    _max_bytes = _kb_import_max_bytes()
    if file.size and file.size > _max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Vault archive too large"
        )

    # Stream upload into memory in chunks, bailing out as soon as the limit is exceeded.
    # Do NOT trust file.size — it may be missing or spoofed.
    buf = io.BytesIO()
    received = 0
    chunk_size = 64 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        received += len(chunk)
        if received > _max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Vault archive too large",
            )
        buf.write(chunk)
    buf.seek(0)

    report = ImportReport(created=0, updated=0, skipped=0, errors=[])

    try:
        with zipfile.ZipFile(buf) as zf:
            kb_import.validate_vault_archive(zf.infolist(), _max_bytes)
            md_files = kb_import.collect_vault_md_files(zf.namelist(), report.errors)

            for md_path in md_files:
                try:
                    async with db.begin_nested():
                        raw = zf.read(md_path).decode("utf-8")
                        fm, body = _parse_frontmatter(raw)

                        parts = Path(md_path).parts
                        section_path_from_zip = (
                            "/" + "/".join(parts[:-1]) if len(parts) > 1 else None
                        )
                        title = fm.get("title") or Path(md_path).stem or "Untitled"
                        tags: list[str] = fm.get("tags") or []
                        section_path = fm.get("section") or section_path_from_zip

                        outcome = await _import_single_article(
                            db, user, redis, title, body, tags, section_path, strategy
                        )
                        if outcome == "skipped":
                            report.skipped += 1
                        elif outcome == "updated":
                            report.updated += 1
                        else:
                            report.created += 1
                except Exception as e:
                    report.errors.append(f"{md_path}: {e}")

        await db.commit()
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid ZIP file"
        ) from exc

    return report


@router.get("/articles/{article_id}/export/pdf", summary="Экспорт статьи в PDF")
async def export_article_pdf(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    article = await _get_article_or_404(db, article_id)
    pdf_perm = await resolve_article_permission(user, article, db, redis)
    if pdf_perm is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient KB permissions"
        )
    if article.status != "published" and pdf_perm not in ("editor", "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.core.pdf import render_pdf

    pdf_bytes = await render_pdf(render_article_html_for_pdf(article))
    filename = f"{kb_export.document_stem(article.title)}.pdf"
    disposition = _rfc5987_filename(filename)
    await _emit_audit(
        redis,
        event_type="kb.article_exported_pdf",
        user_id=str(user.id),
        user_email=user.email,
        resource_id=str(article_id),
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get("/articles/{article_id}/export/docx", summary="Экспорт статьи в DOCX")
async def export_article_docx(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    article = await _get_article_or_404(db, article_id)
    docx_perm = await resolve_article_permission(user, article, db, redis)
    if docx_perm is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient KB permissions"
        )
    if article.status != "published" and docx_perm not in ("editor", "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    docx_bytes = render_article_docx(article)
    filename = f"{kb_export.document_stem(article.title)}.docx"
    disposition = _rfc5987_filename(filename)
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    await _emit_audit(
        redis,
        event_type="kb.article_exported_docx",
        user_id=str(user.id),
        user_email=user.email,
        resource_id=str(article_id),
    )
    return Response(
        content=docx_bytes, media_type=mime, headers={"Content-Disposition": disposition}
    )
