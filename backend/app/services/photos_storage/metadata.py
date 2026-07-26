"""Метаданные изображений фотогалереи: blurhash и EXIF.

Часть пакета :mod:`app.services.photos_storage` (см. его ``__init__``).

``_open_image`` вызывается через namespace пакета
(``from app.services import photos_storage as _ps``), чтобы
``patch("app.services.photos_storage._open_image", ...)`` действовал в runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_GPS_KEYS = {
    "GPSInfo",
    "GPSLatitude",
    "GPSLongitude",
    "GPSAltitude",
    "GPSLatitudeRef",
    "GPSLongitudeRef",
}


def compute_blurhash(image_path: Path) -> str | None:
    """Compute a small blurhash string from an existing image (preferably the 200.webp thumb).

    Returns None on any failure (e.g. unsupported format, broken file).
    """
    try:
        import blurhash as _blurhash
        from PIL import Image  # lazy
    except ImportError:
        # blurhash/PIL не установлены — фича опциональна, не падаем.
        # Логируем на debug: это не runtime-ошибка, а конфигурация окружения.
        logger.debug("photos.blurhash_lib_missing")
        return None
    try:
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
            # Downscale further for speed; blurhash precision unaffected.
            rgb.thumbnail((64, 64), Image.Resampling.LANCZOS)
            encoded: str = _blurhash.encode(rgb, x_components=4, y_components=3)
            return encoded
    except (OSError, ValueError, Image.UnidentifiedImageError) as exc:
        # Повреждённый файл / неподдерживаемый формат / некорректные данные
        # изображения. Audit [H8]: раньше был silent ``except Exception: return
        # None`` — оператор не видел, почему конкретная картинка осталась без
        # blurhash. Debug-лог с путем + классом ошибки даёт diagnostics без
        # спама (один log на каждый проблемный файл при загрузке).
        logger.debug(
            "photos.blurhash_failed",
            path=str(image_path),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None


def extract_exif(
    original_path: Path,
    strip_gps: bool = True,
) -> tuple[dict[str, Any], tuple[int, int] | None, str | None]:
    """Извлекает EXIF, размеры, taken_at (ISO-строка).

    Returns: (exif_dict, (width, height) | None, taken_at_iso | None)
    """
    from PIL import ExifTags  # lazy

    from app.services import photos_storage as _ps

    exif: dict[str, Any] = {}
    size: tuple[int, int] | None = None
    taken_at_iso: str | None = None
    try:
        img = _ps._open_image(original_path)
        size = img.size
        raw = img.getexif()
        if raw:
            for tag_id, val in raw.items():
                tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                if strip_gps and tag in _GPS_KEYS:
                    continue
                try:
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="ignore")
                    exif[tag] = val if isinstance(val, (str, int, float, bool)) else str(val)
                except (UnicodeDecodeError, ValueError, TypeError) as exc:
                    # Один EXIF-тег не декодировался — пропускаем, остальные
                    # остаются. Audit [H8]: debug-лог для диагностики (без него
                    # невозможно понять, какие теги «теряются» на проблемных
                    # файлах). ValueError/TypeError покрывают str(val)-ошибки.
                    logger.debug(
                        "photos.exif_tag_skipped",
                        tag=tag,
                        path=str(original_path),
                        error=str(exc),
                    )
                    continue
            dt = exif.get("DateTimeOriginal") or exif.get("DateTime")
            if isinstance(dt, str):
                # "YYYY:MM:DD HH:MM:SS" → ISO
                try:
                    import datetime as _dt

                    taken_at_iso = _dt.datetime.strptime(dt, "%Y:%m:%d %H:%M:%S").isoformat()
                except ValueError as exc:
                    # Нестандартный формат DateTimeOriginal (не "YYYY:MM:DD
                    # HH:MM:SS") — частая ситуация на старых камерах. Audit
                    # [H8]: debug-лог для диагностики (без него taken_at
                    # «молча» терялся).
                    logger.debug(
                        "photos.exif_taken_at_parse_failed",
                        raw_value=dt,
                        path=str(original_path),
                        error=str(exc),
                    )
                    taken_at_iso = None
    except Exception as exc:
        logger.warning("photos.exif_extract_failed", path=str(original_path), error=str(exc))
    return exif, size, taken_at_iso
