"""Branding asset storage: portal settings file + logo/favicon/login-bg images.

Extracted from ``app.api.branding`` so HTTP handlers stay thin. Owns the
on-disk layout under ``/data/branding`` (``settings.json`` plus the image
assets), the MIME maps and the find/delete/upload primitives.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.logging import get_logger
from app.core.uploads import stream_upload_to_path
from app.schemas.branding import BrandingSettings

logger = get_logger(__name__)

BRANDING_DIR = Path("/data/branding")
SETTINGS_FILE = BRANDING_DIR / "settings.json"
MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2 MB

MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
EXT_TO_MIME: dict[str, str] = {v: k for k, v in MIME_TO_EXT.items()}
ALL_EXTS = list(MIME_TO_EXT.values())

FAVICON_MIME: dict[str, str] = {
    **MIME_TO_EXT,
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}
FAVICON_EXTS = list(FAVICON_MIME.values())

DEFAULT_SETTINGS = BrandingSettings()


def load_settings() -> BrandingSettings:
    if SETTINGS_FILE.exists():
        try:
            return BrandingSettings.model_validate_json(SETTINGS_FILE.read_text("utf-8"))
        except Exception as exc:
            logger.debug("branding.settings_load_failed", error=str(exc))
    return DEFAULT_SETTINGS.model_copy()


def save_settings(s: BrandingSettings) -> None:
    from app.core.system_config import atomic_write

    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(SETTINGS_FILE, s.model_dump_json(indent=2))


def find_file(prefix: str, exts: list[str]) -> Path | None:
    for ext in exts:
        p = BRANDING_DIR / f"{prefix}{ext}"
        if p.exists():
            return p
    return None


def delete_files(prefix: str, exts: list[str]) -> None:
    for ext in exts:
        (BRANDING_DIR / f"{prefix}{ext}").unlink(missing_ok=True)


async def upload_image(
    file: UploadFile,
    prefix: str,
    exts: list[str],
    mime_map: dict[str, str],
    label: str,
) -> str:
    # Pre-check declared MIME — even though stream_upload_to_path re-validates
    # via libmagic, this short-circuits obviously wrong uploads before any I/O.
    content_type = file.content_type
    if content_type is None or content_type not in mime_map:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported format for {label}",
        )
    ext = mime_map[content_type]
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    dest = BRANDING_DIR / f"{prefix}{ext}"
    size, _detected = await stream_upload_to_path(
        file,
        dest,
        max_size=MAX_IMAGE_SIZE,
        allowed_mimes=set(mime_map.keys()),
    )
    # Drop any sibling extensions belonging to the previous upload.
    for other_ext in exts:
        if other_ext != ext:
            (BRANDING_DIR / f"{prefix}{other_ext}").unlink(missing_ok=True)
    logger.info("branding.file_uploaded", prefix=prefix, ext=ext, size=size)
    return f"/api/v1/branding/{prefix.lstrip('/')}"
