"""File icon mapping endpoints.

Stores per-extension SVG icons in ``/data/file-icons/<ext>.svg``. The
mapping IS the filename: an uploaded file at ``docx.svg`` becomes the icon
for any object whose name ends with ``.docx``. Defaults shipped with the
frontend bundle (``frontend/src/assets/file-icons/*.svg``) are used as the
fallback when no override is present.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.api.deps import AdminDep, RedisDep
from app.core.logging import get_logger
from app.core.uploads import stream_upload_to_segments
from app.services.audit import make_audit_emitter

logger = get_logger(__name__)

_emit_audit = make_audit_emitter("file_icons")

router = APIRouter(tags=["files"])

_ICONS_DIR = Path("/data/file-icons")
_MAX_ICON_SIZE = 64 * 1024  # 64 KiB
_ALLOWED_MIMES = {"image/svg+xml", "text/xml", "text/plain"}
_EXT_RE = re.compile(r"^[a-z0-9]{1,16}$")


def _normalize_ext(ext: str) -> str:
    ext = ext.strip().lower().lstrip(".")
    if not _EXT_RE.fullmatch(ext):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Extension must be 1-16 lowercase alphanumeric characters",
        )
    return ext


def _icon_path(ext: str) -> Path:
    return _ICONS_DIR / f"{ext}.svg"


def _list_icons() -> list[dict[str, str | int]]:
    if not _ICONS_DIR.exists():
        return []
    out: list[dict[str, str | int]] = []
    for p in sorted(_ICONS_DIR.glob("*.svg")):
        ext = p.stem.lower()
        if not _EXT_RE.fullmatch(ext):
            continue
        out.append(
            {
                "extension": ext,
                "url": f"/api/v1/files/icons/{ext}",
                "updated_at": int(p.stat().st_mtime),
            }
        )
    return out


@router.get("/files/icons", summary="Список расширений с пользовательскими иконками")
async def list_file_icons() -> dict[str, list[dict[str, str | int]]]:
    return {"items": _list_icons()}


@router.get("/files/icons/{ext}", summary="Получить SVG-иконку для расширения")
@router.head("/files/icons/{ext}", include_in_schema=False)
async def get_file_icon(ext: str, request: Request) -> Response:
    ext = _normalize_ext(ext)
    path = _icon_path(ext)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Icon not set")
    headers = {"Cache-Control": "public, max-age=3600"}
    if request.method == "HEAD":
        return Response(headers={"Content-Type": "image/svg+xml", **headers})
    return FileResponse(path, media_type="image/svg+xml", headers=headers)


@router.post("/admin/files/icons/{ext}", summary="Загрузить SVG-иконку для расширения")
async def upload_file_icon(
    ext: str, file: UploadFile, admin: AdminDep, redis: RedisDep
) -> dict[str, str | int]:
    ext = _normalize_ext(ext)
    if file.content_type and file.content_type not in _ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only SVG files are allowed",
        )
    _ICONS_DIR.mkdir(parents=True, exist_ok=True)
    size, _detected = await stream_upload_to_segments(
        file,
        _ICONS_DIR,
        (f"{ext}.svg",),
        max_size=_MAX_ICON_SIZE,
        allowed_mimes=_ALLOWED_MIMES,
    )
    await _emit_audit(
        redis,
        event_type="file_icons.updated",
        user_id=str(admin.id),
        metadata={"extension": ext},
    )
    logger.info("file_icons.uploaded", extension=ext, size=size)
    return {
        "extension": ext,
        "url": f"/api/v1/files/icons/{ext}",
        "updated_at": int(_icon_path(ext).stat().st_mtime),
    }


@router.delete("/admin/files/icons/{ext}", summary="Удалить пользовательскую иконку")
async def delete_file_icon(ext: str, admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    ext = _normalize_ext(ext)
    path = _icon_path(ext)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Icon not set")
    path.unlink(missing_ok=True)
    await _emit_audit(
        redis,
        event_type="file_icons.deleted",
        user_id=str(admin.id),
        metadata={"extension": ext},
    )
    logger.info("file_icons.deleted", extension=ext)
    return {"detail": "Icon deleted"}
