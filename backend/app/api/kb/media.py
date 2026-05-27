"""KB media (inline images) endpoints."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.system_config import load_system_settings
from app.core.uploads import stream_upload_to_path
from app.schemas.kb_extra import MediaUploadResponse
from app.services.kb_acl import require_article_permission

from ._common import _get_article_or_404

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

KB_MEDIA_DIR = Path(get_settings().kb_media_dir)
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@router.post("/articles/{article_id}/media", response_model=MediaUploadResponse, status_code=201)
async def upload_article_media(
    article_id: uuid.UUID,
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> MediaUploadResponse:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "editor", db, redis)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image extension. Allowed: .jpg, .jpeg, .png, .gif, .webp",
        )

    safe_name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "image").name, flags=re.ASCII)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = KB_MEDIA_DIR / str(article_id) / unique_name

    max_bytes = load_system_settings().kb_media_max_size_mb * 1024 * 1024
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
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    if not re.fullmatch(r"\w[\w.\-]{0,254}", filename) or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    ext = Path(filename).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        mime_type = "image/jpeg"
    elif ext == ".png":
        mime_type = "image/png"
    elif ext == ".gif":
        mime_type = "image/gif"
    elif ext == ".webp":
        mime_type = "image/webp"
    else:
        mime_type = "application/octet-stream"

    internal_path = f"/internal/kb-media/{article_id}/{quote(filename)}"
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": internal_path,
            "Content-Type": mime_type,
            "X-Content-Type-Options": "nosniff",
        },
    )
