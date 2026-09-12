"""Service-link icon storage: MIME mapping, upload, downscaling and cleanup.

Encapsulates the on-disk layout under ``/data/link_icons`` and produces the
``/media/link_icons/{id}.{ext}`` URL consumed by the frontend. The API handler
only persists the returned URL and emits audit.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.logging import get_logger
from app.core.uploads import stream_upload_to_segments

logger = get_logger(__name__)

LINK_ICONS_DIR = Path("/data/link_icons")
ALLOWED_ICON_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/svg+xml",
    "image/x-icon",
    "image/vnd.microsoft.icon",
}
ICON_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
}
MAX_ICON_SIZE = 2 * 1024 * 1024  # 2 MB
_LINK_ICON_TARGET_PX = 128


def remove_icon_files(link_id: uuid.UUID) -> None:
    """Delete any stored icon file for ``link_id`` across all known extensions."""
    LINK_ICONS_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ICON_CONTENT_TYPE_TO_EXT.values():
        p = LINK_ICONS_DIR / f"{link_id}.{ext}"
        p.unlink(missing_ok=True)


def optimize_link_icon(link_id: uuid.UUID, src: Path, ext: str) -> str | None:
    """Downscale raster icons to a small WebP next to the original.

    Returns the new extension to use in icon_url, or None if optimization was
    skipped (vector/ico formats are served as-is).
    """
    if ext in ("svg", "ico"):
        return None
    try:
        from PIL import Image, ImageOps  # lazy import
    except Exception:
        return None
    try:
        with Image.open(src) as src_img:
            pil = ImageOps.exif_transpose(src_img)
            if pil.mode not in ("RGB", "RGBA"):
                pil = pil.convert("RGBA")
            pil.thumbnail((_LINK_ICON_TARGET_PX, _LINK_ICON_TARGET_PX), Image.Resampling.LANCZOS)
            out = LINK_ICONS_DIR / f"{link_id}.webp"
            pil.save(out, "WEBP", quality=85, method=6)
    except Exception as e:
        logger.warning("link.icon.optimize_failed", link_id=str(link_id), error=str(e))
        return None
    if ext != "webp":
        (LINK_ICONS_DIR / f"{link_id}.{ext}").unlink(missing_ok=True)
    return "webp"


async def save_link_icon(file: UploadFile, link_id: uuid.UUID) -> str:
    """Store an uploaded icon (replacing any existing) and return its media URL."""
    content_type = file.content_type or ""
    ext = ICON_CONTENT_TYPE_TO_EXT.get(content_type, "png")

    remove_icon_files(link_id)

    icon_name = f"{link_id}.{ext}"
    await stream_upload_to_segments(
        file,
        LINK_ICONS_DIR,
        (icon_name,),
        max_size=MAX_ICON_SIZE,
        allowed_mimes=ALLOWED_ICON_TYPES,
    )

    # Путь восстановлен из тех же доверенных сегментов (link_id + ext) —
    # нужен для optimize_link_icon ниже.
    dest = LINK_ICONS_DIR / icon_name
    icon_url = f"/media/link_icons/{link_id}.{ext}"
    optimized_ext = optimize_link_icon(link_id, dest, ext)
    if optimized_ext:
        icon_url = f"/media/link_icons/{link_id}.{optimized_ext}"
    return icon_url
