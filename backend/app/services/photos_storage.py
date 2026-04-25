"""Хранение файлов фотогалереи (ADR-031).

Структура на диске:
  /data/photos/originals/{folder_path}/{filename}
  /data/photos/thumbs/{photo_id}/{200|600|1600}.webp

Оригиналы помещаются по иерархии папок (зеркало БД). Thumbnails — плоско по ID.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from app.core.logging import get_logger

logger = get_logger(__name__)

ORIGINALS_ROOT = Path("/data/photos/originals")
THUMBS_ROOT = Path("/data/photos/thumbs")

THUMB_SIZES = (200, 600, 1600)  # widget, grid, lightbox
THUMB_QUALITY = 85

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".tif", ".tiff"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_GPS_KEYS = {"GPSInfo", "GPSLatitude", "GPSLongitude", "GPSAltitude", "GPSLatitudeRef", "GPSLongitudeRef"}


def sanitize_filename(name: str) -> str:
    """Transliterate-free sanitize: keep ASCII letters/digits/._- only.

    Длинные хвосты оборачиваются sha256-суффиксом чтобы не потерять уникальность.
    """
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    base = _SAFE_NAME.sub("-", norm).strip("-._")
    if not base:
        base = "photo"
    if len(base) > 180:
        h = hashlib.sha256(name.encode("utf-8", "ignore")).hexdigest()[:8]
        ext = Path(base).suffix
        base = base[: 160 - len(ext)] + "-" + h + ext
    return base


def is_allowed_ext(name: str) -> bool:
    return Path(name).suffix.lower() in _ALLOWED_EXT


def sanitize_folder_name(name: str) -> str:
    """Sanitize folder name preserving Unicode (Cyrillic etc.).

    Удаляет path-traversal и OS-reserved символы, оставляя кириллицу/пробелы.
    """
    norm = unicodedata.normalize("NFC", name or "").strip()
    cleaned = _INVALID_FS.sub("-", norm).strip(". ")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if not cleaned or cleaned in {".", ".."}:
        cleaned = "folder"
    if len(cleaned) > 200:
        h = hashlib.sha256((name or "").encode("utf-8", "ignore")).hexdigest()[:8]
        cleaned = cleaned[:180] + "-" + h
    return cleaned


def folder_fs_path(folder_fs_path_str: str) -> Path:
    """Конвертирует материализованный fs_path (Unicode) в безопасный путь на диске."""
    parts = [p for p in (folder_fs_path_str or "").split("/") if p and p not in {".", ".."}]
    p = ORIGINALS_ROOT.joinpath(*parts) if parts else ORIGINALS_ROOT
    # Защита от path traversal
    p = p.resolve()
    if not str(p).startswith(str(ORIGINALS_ROOT.resolve())):
        raise ValueError("Invalid folder path")
    return p


def rename_folder_dir(old_fs_path: str, new_fs_path: str) -> None:
    """Переименовать каталог на диске при изменении имени/перемещении папки."""
    if not old_fs_path or old_fs_path == new_fs_path:
        return
    old = folder_fs_path(old_fs_path)
    new = folder_fs_path(new_fs_path)
    if not old.exists():
        return
    new.parent.mkdir(parents=True, exist_ok=True)
    if new.exists():
        # Назначение существует — переносим содержимое и удаляем пустой источник.
        import shutil as _sh
        for child in old.iterdir():
            target = new / child.name
            if not target.exists():
                _sh.move(str(child), str(target))
        try:
            old.rmdir()
        except OSError:
            pass
    else:
        import shutil as _sh
        _sh.move(str(old), str(new))


def _unique_name(target_dir: Path, original_name: str) -> str:
    safe = sanitize_filename(original_name)
    stem = Path(safe).stem
    ext = Path(safe).suffix.lower() or ".bin"
    candidate = safe
    i = 1
    while (target_dir / candidate).exists():
        candidate = f"{stem}-{i}{ext}"
        i += 1
        if i > 9999:
            candidate = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
            break
    return candidate


def save_original(folder_path: str, original_name: str, data: bytes | BinaryIO) -> tuple[str, int]:
    """Сохраняет оригинал, возвращает (filename_on_disk, size_bytes)."""
    target_dir = folder_fs_path(folder_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = _unique_name(target_dir, original_name)
    fpath = target_dir / fname

    if isinstance(data, bytes):
        fpath.write_bytes(data)
        size = len(data)
    else:
        size = 0
        with fpath.open("wb") as out:
            while True:
                chunk = data.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                size += len(chunk)
    return fname, size


def _open_image(path: Path):
    # pillow-heif регистрирует HEIF через register_heif_opener; если не доступен — игнорируем.
    try:
        from pillow_heif import register_heif_opener  # type: ignore
        register_heif_opener()
    except Exception:
        pass
    from PIL import Image  # lazy import
    img = Image.open(path)
    img.load()
    return img


def generate_thumbnails(photo_id: uuid.UUID, original_path: Path) -> dict[int, Path]:
    """Генерирует thumbnails трёх размеров в WebP.

    Сохраняет в /data/photos/thumbs/{photo_id}/{size}.webp.
    Возвращает dict{size: path}.
    """
    from PIL import Image, ImageOps  # lazy

    out_dir = THUMBS_ROOT / str(photo_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    img = _open_image(original_path)
    # Применяем EXIF-ориентацию чтобы thumbnails были правильно повернуты.
    img = ImageOps.exif_transpose(img)
    # Переводим в RGB для WebP (alpha пропустим для простоты).
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    result: dict[int, Path] = {}
    for size in THUMB_SIZES:
        copy = img.copy()
        copy.thumbnail((size, size), Image.Resampling.LANCZOS)
        out_path = out_dir / f"{size}.webp"
        save_kwargs = {"quality": THUMB_QUALITY, "method": 6}
        copy.save(out_path, "WEBP", **save_kwargs)
        result[size] = out_path
    return result


def extract_exif(original_path: Path, strip_gps: bool = True) -> tuple[dict, tuple[int, int] | None, str | None]:
    """Извлекает EXIF, размеры, taken_at (ISO-строка).

    Returns: (exif_dict, (width, height) | None, taken_at_iso | None)
    """
    from PIL import ExifTags, Image  # lazy

    exif: dict = {}
    size: tuple[int, int] | None = None
    taken_at_iso: str | None = None
    try:
        img = _open_image(original_path)
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
                except Exception:
                    continue
            dt = exif.get("DateTimeOriginal") or exif.get("DateTime")
            if isinstance(dt, str):
                # "YYYY:MM:DD HH:MM:SS" → ISO
                try:
                    import datetime as _dt
                    taken_at_iso = _dt.datetime.strptime(dt, "%Y:%m:%d %H:%M:%S").isoformat()
                except Exception:
                    taken_at_iso = None
    except Exception as exc:
        logger.warning("photos.exif_extract_failed", path=str(original_path), error=str(exc))
    return exif, size, taken_at_iso


def delete_photo_files(original_path: Path | None, photo_id: uuid.UUID) -> None:
    try:
        if original_path and original_path.exists():
            original_path.unlink()
    except OSError:
        pass
    try:
        d = THUMBS_ROOT / str(photo_id)
        if d.exists():
            for f in d.iterdir():
                try:
                    f.unlink()
                except OSError:
                    pass
            d.rmdir()
    except OSError:
        pass


def thumb_path(photo_id: uuid.UUID, size: int) -> Path:
    if size not in THUMB_SIZES:
        raise ValueError(f"Invalid thumbnail size: {size}")
    return THUMBS_ROOT / str(photo_id) / f"{size}.webp"
