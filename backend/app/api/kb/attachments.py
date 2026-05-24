"""KB article file attachments endpoints."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.system_config import load_system_settings
from app.core.uploads import stream_upload_to_path
from app.models.kb import KbArticleFile
from app.schemas.kb_extra import KbFileList, KbFilePublic
from app.services.audit import push_audit_event
from app.services.kb_acl import perm_gte, require_article_permission, resolve_article_permission

from ._common import _get_article_or_404, _rfc5987_filename

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

KB_FILES_DIR = Path(get_settings().kb_files_dir)

SAFE_MIME_TYPES = {
    # Images
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    # Documents
    "application/pdf",
    "text/plain",
    "text/csv",
    # MS Office & OpenOffice
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    # Archives
    "application/zip",
    "application/x-zip-compressed",
    "application/x-tar",
    "application/x-gzip",
    "application/x-bzip2",
    "application/x-7z-compressed",
    "application/x-rar-compressed",
    # JSON / Data
    "application/json",
}


@router.get("/articles/{article_id}/files", response_model=KbFileList)
async def list_article_files(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbFileList:
    article = await _get_article_or_404(db, article_id)
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
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "editor", db, redis)

    original_name = file.filename or "file"
    safe_stored = f"{uuid.uuid4().hex}_{re.sub(r'[^\\w.\\-]', '_', Path(original_name).name)}"
    dest = KB_FILES_DIR / str(article_id) / safe_stored

    max_bytes = load_system_settings().kb_attachment_max_size_mb * 1024 * 1024
    size, mime = await stream_upload_to_path(file, dest, max_size=max_bytes)

    effective_mime = mime or file.content_type
    if not effective_mime or effective_mime not in SAFE_MIME_TYPES:
        stored_mime = "application/octet-stream"
    else:
        stored_mime = effective_mime

    kb_file = KbArticleFile(
        article_id=article_id,
        filename=safe_stored,
        original_name=original_name,
        size_bytes=size,
        mime_type=stored_mime,
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
    article = await _get_article_or_404(db, article_id)

    perm = await resolve_article_permission(user, article, db, redis)
    is_uploader_res = await db.execute(
        select(KbArticleFile.uploaded_by).where(KbArticleFile.id == file_id)
    )
    uploader_row = is_uploader_res.fetchone()
    is_owner = uploader_row and uploader_row[0] == user.id

    if not perm_gte(perm, "editor") and not is_owner and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    f_res = await db.execute(
        select(KbArticleFile).where(
            KbArticleFile.id == file_id, KbArticleFile.article_id == article_id
        )
    )
    kb_file = f_res.scalar_one_or_none()
    if not kb_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    disk_path = KB_FILES_DIR / str(article_id) / kb_file.filename
    await db.delete(kb_file)
    await db.commit()
    disk_path.unlink(missing_ok=True)


@router.get("/files/{article_id}/{filename}")
async def download_article_file(
    article_id: uuid.UUID,
    filename: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    f_res = await db.execute(
        select(KbArticleFile).where(
            KbArticleFile.article_id == article_id,
            KbArticleFile.filename == filename,
        )
    )
    kb_file = f_res.scalar_one_or_none()
    if not kb_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,254}", filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    should_push = True
    try:
        redis_key = f"kb:audit:download:{user.id}:{kb_file.id}"
        # Атомарный SET NX EX: запись попадёт в журнал только если ключ был свободен.
        acquired = await redis.set(redis_key, "1", ex=300, nx=True)
        if not acquired:
            should_push = False
    except Exception:
        pass

    if should_push:
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
            "X-Content-Type-Options": "nosniff",
        },
    )
