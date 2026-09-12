"""Обложки курсов модуля обучения (этап 2; ТЗ §6.2 по образцу news-covers).

Хранение — локально ``/data/learning/covers/`` (третий легитимный локальный
корень §1, том ``/data/learning`` уже смонтирован контурам деплоя). Оригинал
после обработки не хранится: остаётся один WebP-превью шириной до
``COVER_MAX_WIDTH``. Раздача — через API с проверкой прав (методист либо
зачисленный участник опубликованного курса), как PDF материалов: nginx
learn-контура проксирует только ``/api/v1/learning/``, отдельной статики у
модуля нет.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.uploads import stream_upload_to_segments
from app.models.learning import LearningCourse
from app.services.learning import courses_service as cs

logger = get_logger(__name__)

COVER_MAX_BYTES = 5 * 1024 * 1024
ALLOWED_COVER_MIMES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_COVER_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
COVER_MAX_WIDTH = 1200
_COVER_QUALITY = 82


def covers_dir() -> Path:
    return Path(cs.LEARNING_DATA_DIR) / "covers"


def cover_preview_path(course_id: uuid.UUID) -> Path:
    return covers_dir() / f"{course_id}.webp"


def resolve_cover_path(course: LearningCourse) -> Path | None:
    """Канонический путь превью или None. ``cover_path`` заполняется только
    сервером; проверка соответствия страхует от подмены значения в БД напрямую
    (тот же приём, что у PDF материалов)."""
    if not course.cover_path:
        return None
    expected = cover_preview_path(course.id)
    path = Path(course.cover_path)
    if path != expected or not path.is_file():
        return None
    return path


def build_cover_preview(src: Path, dest: Path) -> None:
    """WebP-превью по образцу news-covers: EXIF-поворот, приведение режимов
    (прозрачный P/RGBA сохраняется, остальное — RGB), ланцош-даунскейл."""
    from PIL import Image, ImageOps

    with Image.open(src) as src_img:
        pil = ImageOps.exif_transpose(src_img)
        if pil.mode == "P":
            pil = pil.convert("RGBA" if "transparency" in pil.info else "RGB")
        elif pil.mode not in ("RGB", "RGBA"):
            pil = pil.convert("RGB")
        if pil.width > COVER_MAX_WIDTH:
            pil.thumbnail((COVER_MAX_WIDTH, COVER_MAX_WIDTH * 4), Image.Resampling.LANCZOS)
        pil.save(dest, "WEBP", quality=_COVER_QUALITY, method=6)


async def file_response(path: Path) -> StreamingResponse:
    """Раздача превью стримингом (прецедент PDF материалов; не FileResponse)."""

    async def chunk_iter() -> AsyncIterator[bytes]:
        import aiofiles

        async with aiofiles.open(path, "rb") as f:
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        chunk_iter(),
        media_type="image/webp",
        headers={
            # Превью иммутабельно для своей версии: URL содержит ?v=<updated_at>
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _cleanup_except_preview(course_id: uuid.UUID) -> None:
    """Промежуточный staging-файл и обложки прежних загрузок — мусор."""
    preview = cover_preview_path(course_id)
    if not covers_dir().exists():
        return
    for p in covers_dir().glob(f"{course_id}.*"):
        if p != preview:
            with contextlib.suppress(OSError):
                p.unlink()


async def upload_cover(
    db: AsyncSession, course: LearningCourse, file: UploadFile
) -> LearningCourse:
    """Валидация → стриминг во временный файл → Pillow-превью → путь в БД.

    Заявленный и реальный (python-magic) MIME проверяются внутри
    ``stream_upload_to_segments``; обработка Pillow — в отдельном потоке,
    чтобы не блокать цикл событий."""
    if file.content_type not in ALLOWED_COVER_MIMES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Поддерживаются изображения JPEG, PNG, WebP или GIF",
        )
    ext = _COVER_EXT_BY_MIME[file.content_type]
    covers_dir().mkdir(parents=True, exist_ok=True)
    staged = covers_dir() / f"{course.id}.staging.{ext}"
    await stream_upload_to_segments(
        file,
        covers_dir(),
        (staged.name,),
        max_size=COVER_MAX_BYTES,
        allowed_mimes=ALLOWED_COVER_MIMES,
    )
    dest = cover_preview_path(course.id)
    try:
        await asyncio.to_thread(build_cover_preview, staged, dest)
    except Exception as exc:
        logger.warning("learning.cover_preview_failed", course_id=str(course.id), error=str(exc))
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Не удалось обработать изображение",
        ) from exc
    finally:
        with contextlib.suppress(OSError):
            staged.unlink(missing_ok=True)
    _cleanup_except_preview(course.id)
    course.cover_path = str(dest)
    course.updated_at = datetime.now(UTC)
    await db.flush()
    logger.info("learning.cover_uploaded", course_id=str(course.id))
    return course


async def delete_cover(db: AsyncSession, course: LearningCourse) -> LearningCourse:
    """Снять обложку: файлы (превью + остатки staging) удаляются, путь чистится."""
    if covers_dir().exists():
        for p in covers_dir().glob(f"{course.id}.*"):
            with contextlib.suppress(OSError):
                p.unlink()
    course.cover_path = None
    course.updated_at = datetime.now(UTC)
    await db.flush()
    logger.info("learning.cover_deleted", course_id=str(course.id))
    return course
