"""Users API: аватары — общая логика загрузки/удаления для /me и /admin.

Файлы живут в ``/data/avatars`` (том, отдаёт nginx — ``/media/avatars/``).
Имя файла версионировано: ``{user_id}_{ms}.webp`` — каждая загрузка даёт новый
URL, поэтому nginx-кэш (7 дней) не мешает обновлению, а старые файлы
``{user_id}_*`` удаляются сразу после успешной конвертации.

Конвертация: Pillow → WebP, длинная сторона ≤ 512 px (аватар показывается
кружком ≤ 96 px, детализация выше не нужна; см. паттерн ``news/_helpers.py``).
Позиционирование — фокальная точка + зум в БД (``avatar_focal_*``), файл не
режется; при новой загрузке фокал сбрасывается в NULL (= центр/100%).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uploads import safe_join_within, stream_upload_to_segments
from app.models.user import User

from . import users_repo
from ._common import (
    ALLOWED_IMG_TYPES,
    AVATARS_DIR,
    CONTENT_TYPE_TO_EXT,
    MAX_AVATAR_SIZE,
    logger,
)

AVATAR_MAX_DIM = 512
AVATAR_WEBP_QUALITY = 85


def _remove_avatar_files(user_id: uuid.UUID, keep: str | None = None) -> None:
    """Удалить все файлы аватаров пользователя (кроме ``keep``).

    Покрывает и легаси-имена ``{user_id}.{ext}`` (до конвертации в WebP), и
    версионированные ``{user_id}_{ms}.webp``, и временные ``{user_id}_tmp_*``.
    """
    if not AVATARS_DIR.exists():
        return
    for pattern in (f"{user_id}.*", f"{user_id}_*"):
        for p in AVATARS_DIR.glob(pattern):
            if keep is not None and p.name == keep:
                continue
            p.unlink(missing_ok=True)


def _convert_to_webp(src: Path, dst: Path) -> None:
    from PIL import Image, ImageOps  # lazy

    with Image.open(src) as img:
        pil = ImageOps.exif_transpose(img)
        if pil.mode == "P":
            pil = pil.convert("RGBA" if "transparency" in pil.info else "RGB")
        elif pil.mode not in ("RGB", "RGBA"):
            pil = pil.convert("RGB")
        pil.thumbnail((AVATAR_MAX_DIM, AVATAR_MAX_DIM), Image.Resampling.LANCZOS)
        pil.save(dst, "WEBP", quality=AVATAR_WEBP_QUALITY, method=6)


async def save_avatar(db: AsyncSession, target: User, file: UploadFile) -> User:
    """Валидирует, конвертирует в WebP ≤512px и сохраняет аватар пользователя."""
    if file.content_type not in ALLOWED_IMG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported image type",
        )

    ext = CONTENT_TYPE_TO_EXT.get(file.content_type or "", "jpg")
    ts = time.time_ns() // 1_000_000
    tmp_name = f"{target.id}_tmp_{ts}.{ext}"
    final_name = f"{target.id}_{ts}.webp"

    await stream_upload_to_segments(
        file,
        AVATARS_DIR,
        (tmp_name,),
        max_size=MAX_AVATAR_SIZE,
        allowed_mimes=ALLOWED_IMG_TYPES,
    )
    tmp_path = safe_join_within(AVATARS_DIR, tmp_name)
    final_path = safe_join_within(AVATARS_DIR, final_name)
    try:
        await asyncio.to_thread(_convert_to_webp, tmp_path, final_path)
    except Exception as e:
        logger.warning("avatar.convert_failed", user_id=str(target.id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid image",
        ) from e
    finally:
        tmp_path.unlink(missing_ok=True)

    _remove_avatar_files(target.id, keep=final_name)

    avatar_url = f"/media/avatars/{final_name}"
    await users_repo.update_user_fields(
        db,
        target.id,
        {
            "avatar_url": avatar_url,
            "avatar_focal_x": None,
            "avatar_focal_y": None,
            "avatar_focal_zoom": None,
        },
    )
    await db.commit()
    await db.refresh(target)
    return target


async def remove_avatar(db: AsyncSession, target: User) -> User:
    """Удаляет файлы аватара и чистит ``avatar_url`` + фокал в БД."""
    _remove_avatar_files(target.id)
    await users_repo.update_user_fields(
        db,
        target.id,
        {
            "avatar_url": None,
            "avatar_focal_x": None,
            "avatar_focal_y": None,
            "avatar_focal_zoom": None,
        },
    )
    await db.commit()
    await db.refresh(target)
    return target
