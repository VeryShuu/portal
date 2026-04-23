"""Branding endpoints: logo, favicon, login background, portal settings."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import AdminDep
from app.core.logging import get_logger
from app.core.uploads import stream_upload_to_path

logger = get_logger(__name__)

router = APIRouter(tags=["branding"])

_BRANDING_DIR = Path("/data/branding")
_SETTINGS_FILE = _BRANDING_DIR / "settings.json"
_MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2 MB

_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
_EXT_TO_MIME: dict[str, str] = {v: k for k, v in _MIME_TO_EXT.items()}
_ALL_EXTS = list(_MIME_TO_EXT.values())

_FAVICON_MIME: dict[str, str] = {
    **_MIME_TO_EXT,
    "image/x-icon": ".ico",
}
_FAVICON_EXTS = list(_FAVICON_MIME.values())


class BrandingSettings(BaseModel):
    portal_name: str = "Корпоративный портал"
    portal_tagline: str = ""
    accent_color: str = "#d8262c"
    welcome_subtitle: str = ""
    banner_enabled: bool = False
    banner_text: str = ""
    banner_type: Literal["info", "warning", "error", "success"] = "info"
    banner_expires_at: str | None = None


_DEFAULT_SETTINGS = BrandingSettings()


def _load_settings() -> BrandingSettings:
    if _SETTINGS_FILE.exists():
        try:
            return BrandingSettings.model_validate_json(_SETTINGS_FILE.read_text("utf-8"))
        except Exception:
            pass
    return _DEFAULT_SETTINGS.model_copy()


def _save_settings(s: BrandingSettings) -> None:
    _BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(s.model_dump_json(indent=2), encoding="utf-8")


def _find_file(prefix: str, exts: list[str]) -> Path | None:
    for ext in exts:
        p = _BRANDING_DIR / f"{prefix}{ext}"
        if p.exists():
            return p
    return None


def _delete_files(prefix: str, exts: list[str]) -> None:
    for ext in exts:
        (_BRANDING_DIR / f"{prefix}{ext}").unlink(missing_ok=True)


async def _upload_image(
    file: UploadFile,
    prefix: str,
    exts: list[str],
    mime_map: dict[str, str],
    label: str,
) -> str:
    # Pre-check declared MIME — even though stream_upload_to_path re-validates
    # via libmagic, this short-circuits obviously wrong uploads before any I/O.
    if file.content_type not in mime_map:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported format for {label}",
        )
    ext = mime_map[file.content_type]
    _BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    dest = _BRANDING_DIR / f"{prefix}{ext}"
    size, _detected = await stream_upload_to_path(
        file,
        dest,
        max_size=_MAX_IMAGE_SIZE,
        allowed_mimes=set(mime_map.keys()),
    )
    # Drop any sibling extensions belonging to the previous upload.
    for other_ext in exts:
        if other_ext != ext:
            (_BRANDING_DIR / f"{prefix}{other_ext}").unlink(missing_ok=True)
    logger.info("branding.file_uploaded", prefix=prefix, ext=ext, size=size)
    return f"/api/v1/branding/{prefix.lstrip('/')}"


# ── Settings ─────────────────────────────────────────────────────────────────

@router.get("/branding/settings", summary="Настройки оформления портала")
async def get_settings() -> BrandingSettings:
    return _load_settings()


@router.put("/admin/branding/settings", summary="Сохранить настройки оформления")
async def save_settings(body: BrandingSettings, _admin: AdminDep) -> BrandingSettings:
    _save_settings(body)
    logger.info("branding.settings_saved")
    return body


# ── Logo ─────────────────────────────────────────────────────────────────────

@router.get("/branding/logo", summary="Получить логотип портала")
async def get_logo() -> FileResponse:
    logo = _find_file("logo", _ALL_EXTS)
    if not logo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No custom logo set")
    mime = _EXT_TO_MIME.get(logo.suffix, "image/png")
    return FileResponse(logo, media_type=mime, headers={"Cache-Control": "public, max-age=300"})


@router.post("/admin/branding/logo", summary="Загрузить логотип портала")
async def upload_logo(file: UploadFile, _admin: AdminDep) -> dict:
    url = await _upload_image(file, "logo", _ALL_EXTS, _MIME_TO_EXT, "logo")
    return {"url": url}


@router.delete("/admin/branding/logo", summary="Сбросить логотип к умолчанию")
async def reset_logo(_admin: AdminDep) -> dict:
    _delete_files("logo", _ALL_EXTS)
    logger.info("branding.logo_reset")
    return {"detail": "Logo reset to default"}


# ── Favicon ───────────────────────────────────────────────────────────────────

@router.get("/branding/favicon", summary="Получить favicon портала")
async def get_favicon() -> FileResponse:
    fav = _find_file("favicon", _FAVICON_EXTS)
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No custom favicon set")
    mime = _EXT_TO_MIME.get(fav.suffix) or ("image/x-icon" if fav.suffix == ".ico" else "image/png")
    return FileResponse(fav, media_type=mime, headers={"Cache-Control": "public, max-age=3600"})


@router.post("/admin/branding/favicon", summary="Загрузить favicon портала")
async def upload_favicon(file: UploadFile, _admin: AdminDep) -> dict:
    url = await _upload_image(file, "favicon", _FAVICON_EXTS, _FAVICON_MIME, "favicon")
    return {"url": url}


@router.delete("/admin/branding/favicon", summary="Сбросить favicon к умолчанию")
async def reset_favicon(_admin: AdminDep) -> dict:
    _delete_files("favicon", _FAVICON_EXTS)
    logger.info("branding.favicon_reset")
    return {"detail": "Favicon reset to default"}


# ── Login background ──────────────────────────────────────────────────────────

@router.get("/branding/login-bg", summary="Получить фон страницы входа")
async def get_login_bg() -> FileResponse:
    bg = _find_file("login-bg", _ALL_EXTS)
    if not bg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No custom login background set")
    mime = _EXT_TO_MIME.get(bg.suffix, "image/jpeg")
    return FileResponse(bg, media_type=mime, headers={"Cache-Control": "public, max-age=3600"})


@router.post("/admin/branding/login-bg", summary="Загрузить фон страницы входа")
async def upload_login_bg(file: UploadFile, _admin: AdminDep) -> dict:
    url = await _upload_image(file, "login-bg", _ALL_EXTS, _MIME_TO_EXT, "login-bg")
    return {"url": url}


@router.delete("/admin/branding/login-bg", summary="Сбросить фон страницы входа")
async def reset_login_bg(_admin: AdminDep) -> dict:
    _delete_files("login-bg", _ALL_EXTS)
    logger.info("branding.login_bg_reset")
    return {"detail": "Login background reset to default"}
