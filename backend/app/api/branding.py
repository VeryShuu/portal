"""Branding endpoints: logo upload and serve."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import AdminDep
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["branding"])

_BRANDING_DIR = Path("/data/branding")
_MAX_SIZE = 2 * 1024 * 1024  # 2 MB

_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
_EXT_TO_MIME: dict[str, str] = {v: k for k, v in _MIME_TO_EXT.items()}
_ALL_EXTS = list(_MIME_TO_EXT.values())


def _current_logo() -> Path | None:
    for ext in _ALL_EXTS:
        p = _BRANDING_DIR / f"logo{ext}"
        if p.exists():
            return p
    return None


@router.get("/branding/logo", summary="Получить логотип портала")
async def get_logo() -> FileResponse:
    logo = _current_logo()
    if not logo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No custom logo set")
    mime = _EXT_TO_MIME.get(logo.suffix, "image/png")
    return FileResponse(logo, media_type=mime, headers={"Cache-Control": "public, max-age=300"})


@router.post("/admin/branding/logo", summary="Загрузить логотип портала")
async def upload_logo(file: UploadFile, _admin: AdminDep) -> dict:
    if file.content_type not in _MIME_TO_EXT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported format. Use PNG, JPEG, SVG or WebP",
        )
    content = await file.read()
    if len(content) > _MAX_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Max logo size is 2 MB")

    _BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    for ext in _ALL_EXTS:
        (_BRANDING_DIR / f"logo{ext}").unlink(missing_ok=True)

    ext = _MIME_TO_EXT[file.content_type]
    (_BRANDING_DIR / f"logo{ext}").write_bytes(content)
    logger.info("branding.logo_uploaded", ext=ext, size=len(content))
    return {"url": "/api/v1/branding/logo"}


@router.delete("/admin/branding/logo", summary="Сбросить логотип к умолчанию")
async def reset_logo(_admin: AdminDep) -> dict:
    for ext in _ALL_EXTS:
        (_BRANDING_DIR / f"logo{ext}").unlink(missing_ok=True)
    logger.info("branding.logo_reset")
    return {"detail": "Logo reset to default"}
