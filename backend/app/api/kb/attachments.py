"""KB article file attachments endpoints."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import cast

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.system_config import load_system_settings
from app.core.uploads import stream_upload_to_segments
from app.models.kb import KbArticleFile
from app.schemas.kb_extra import KbFileList, KbFilePublic
from app.services.audit import make_audit_emitter
from app.services.kb_acl import perm_gte, require_article_permission, resolve_article_permission
from app.services.kb_trash import try_remove_empty_article_dir

from . import attachments_repo
from ._common import _get_article_or_404, _rfc5987_filename

_emit_audit = make_audit_emitter("kb_article")

logger = get_logger(__name__)

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

    files = await attachments_repo.list_files(db, article_id)
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

    max_bytes = load_system_settings().kb_attachment_max_size_mb * 1024 * 1024
    size, mime = await stream_upload_to_segments(
        file,
        KB_FILES_DIR,
        (str(article_id), safe_stored),
        max_size=max_bytes,
        allowed_mimes=SAFE_MIME_TYPES,
    )

    stored_mime = mime or file.content_type or "application/octet-stream"

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
    await _emit_audit(
        redis,
        event_type="kb.file_upload",
        user_id=str(user.id),
        resource_id=str(article_id),
        metadata={"filename": original_name, "size_bytes": size},
    )
    return cast(KbFilePublic, KbFilePublic.model_validate(kb_file))


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
    uploader_id = await attachments_repo.get_file_uploader(db, file_id)
    is_owner = uploader_id is not None and uploader_id == user.id

    if not perm_gte(perm, "editor") and not is_owner and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    kb_file = await attachments_repo.get_file(db, article_id=article_id, file_id=file_id)
    if not kb_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    disk_path = KB_FILES_DIR / str(article_id) / kb_file.filename
    await db.delete(kb_file)
    await db.commit()
    disk_path.unlink(missing_ok=True)
    await try_remove_empty_article_dir(article_id, "files")


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

    kb_file = await attachments_repo.get_file_by_name(db, article_id=article_id, filename=filename)
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
    except Exception as exc:
        logger.debug("kb.attachments.audit_ratelimit_failed", error=str(exc))

    if should_push:
        await _emit_audit(
            redis,
            event_type="kb.file_download",
            user_id=str(user.id),
            resource_id=str(article_id),
            resource_title=kb_file.original_name,
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
