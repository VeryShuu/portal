"""Object-directory entry avatar storage: upload, downscale and cleanup.

Mirrors :mod:`app.services.link_icon`: stores one image per entry under
``/data/directory_avatars`` and produces the ``/media/directory_avatars/{id}.{ext}``
URL consumed by the frontend. Real MIME is validated via python-magic by the
streaming uploader; the API handler only persists the returned path.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.logging import get_logger
from app.core.uploads import stream_upload_to_path

logger = get_logger(__name__)

DIRECTORY_AVATARS_DIR = Path("/data/directory_avatars")
ALLOWED_AVATAR_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
AVATAR_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB
_AVATAR_TARGET_PX = 400


def remove_avatar_files(entry_id: uuid.UUID) -> None:
    """Delete any stored avatar file for ``entry_id`` across known extensions."""
    DIRECTORY_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    for ext in AVATAR_CONTENT_TYPE_TO_EXT.values():
        (DIRECTORY_AVATARS_DIR / f"{entry_id}.{ext}").unlink(missing_ok=True)


def _optimize_avatar(entry_id: uuid.UUID, src: Path, ext: str) -> str | None:
    """Downscale the avatar to a square-ish WebP; return the new ext or None."""
    try:
        from PIL import Image, ImageOps  # lazy import
    except Exception:
        return None
    try:
        with Image.open(src) as src_img:
            pil = ImageOps.exif_transpose(src_img)
            if pil.mode not in ("RGB", "RGBA"):
                pil = pil.convert("RGB")
            pil.thumbnail((_AVATAR_TARGET_PX, _AVATAR_TARGET_PX), Image.Resampling.LANCZOS)
            out = DIRECTORY_AVATARS_DIR / f"{entry_id}.webp"
            pil.save(out, "WEBP", quality=85, method=6)
    except Exception as e:
        logger.warning("directory.avatar.optimize_failed", entry_id=str(entry_id), error=str(e))
        return None
    if ext != "webp":
        (DIRECTORY_AVATARS_DIR / f"{entry_id}.{ext}").unlink(missing_ok=True)
    return "webp"


async def save_avatar(file: UploadFile, entry_id: uuid.UUID) -> str:
    """Store an uploaded avatar (replacing any existing) and return its media URL."""
    content_type = file.content_type or ""
    ext = AVATAR_CONTENT_TYPE_TO_EXT.get(content_type, "png")

    remove_avatar_files(entry_id)

    dest = DIRECTORY_AVATARS_DIR / f"{entry_id}.{ext}"
    await stream_upload_to_path(
        file,
        dest,
        max_size=MAX_AVATAR_SIZE,
        allowed_mimes=ALLOWED_AVATAR_TYPES,
    )

    avatar_url = f"/media/directory_avatars/{entry_id}.{ext}"
    optimized_ext = _optimize_avatar(entry_id, dest, ext)
    if optimized_ext:
        avatar_url = f"/media/directory_avatars/{entry_id}.{optimized_ext}"
    return avatar_url
