"""Хранение файлов фотогалереи (ADR-031).

Структура на диске:
  /data/photos/originals/{folder_path}/{filename}
  /data/photos/thumbs/{photo_id}/{200|600|1600}.webp

Оригиналы помещаются по иерархии папок (зеркало БД). Thumbnails — плоско по ID.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import unicodedata
import uuid
from pathlib import Path
from typing import BinaryIO

from app.core.logging import get_logger

logger = get_logger(__name__)

ORIGINALS_ROOT = Path("/data/photos/originals")
THUMBS_ROOT = Path("/data/photos/thumbs")
IMPORT_ROOT = Path("/data/photos/import")
ZIPS_ROOT = Path("/data/photos/zips")

# Разрешённые корневые директории для path-validation
_ALLOWED_ROOTS = (ORIGINALS_ROOT, IMPORT_ROOT, ZIPS_ROOT)

THUMB_SIZES = (200, 400, 600, 1000, 1600)  # widget, grid, lightbox
THUMB_QUALITY = 85

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".tif", ".tiff"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_GPS_KEYS = {
    "GPSInfo",
    "GPSLatitude",
    "GPSLongitude",
    "GPSAltitude",
    "GPSLatitudeRef",
    "GPSLongitudeRef",
}


def sanitize_filename(name: str) -> str:
    """Transliterate-free sanitize: keep ASCII letters/digits/._- only.

    Длинные хвосты оборачиваются sha256-суффиксом чтобы не потерять уникальность.
    """
    p = Path(name)
    ext = p.suffix
    stem = p.stem if p.stem else name

    norm_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    base = _SAFE_NAME.sub("-", norm_stem).strip("-._")
    if not base:
        base = "photo"

    if ext:
        norm_ext = unicodedata.normalize("NFKD", ext).encode("ascii", "ignore").decode("ascii")
        norm_ext = _SAFE_NAME.sub("", norm_ext)
        if norm_ext and not norm_ext.startswith("."):
            norm_ext = "." + norm_ext
    else:
        norm_ext = ""

    result = base + norm_ext
    if len(result) > 180:
        h = hashlib.sha256(name.encode("utf-8", "ignore")).hexdigest()[:8]
        base = base[: 160 - len(norm_ext)] + "-" + h
        result = base + norm_ext
    return result


def is_allowed_ext(name: str) -> bool:
    return Path(name).suffix.lower() in _ALLOWED_EXT


def sanitize_folder_name(name: str) -> str:
    """Sanitize folder name preserving Unicode (Cyrillic etc.).

    Удаляет path-traversal и OS-reserved символы, оставляя кириллицу/пробелы.
    """
    norm = unicodedata.normalize("NFC", name or "").strip()
    cleaned = _INVALID_FS.sub("-", norm).strip(". ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if not cleaned or cleaned in {".", ".."}:
        cleaned = "folder"
    if len(cleaned) > 200:
        h = hashlib.sha256((name or "").encode("utf-8", "ignore")).hexdigest()[:8]
        cleaned = cleaned[:180] + "-" + h
    return cleaned


def folder_fs_path(folder_fs_path_str: str) -> Path:
    """Конвертирует fs_path в безопасный абсолютный путь на диске.

    Поддерживает два формата:
    - Относительный путь (для обычных папок) → разрешается относительно ORIGINALS_ROOT.
    - Абсолютный путь (для импортированных папок) → валидируется по _ALLOWED_ROOTS.
    """
    fs = folder_fs_path_str or ""
    if Path(fs).is_absolute() or fs.startswith("/"):
        # Абсолютный путь — проверяем что он внутри одного из разрешённых корней
        p = Path(fs).resolve()
        for allowed in _ALLOWED_ROOTS:
            if str(p).startswith(str(allowed.resolve())):
                return p
        raise ValueError("Invalid folder path")
    # Относительный путь → ORIGINALS_ROOT, резолвим ".." вручную
    parts = [seg for seg in fs.replace("\\", "/").split("/") if seg and seg != "."]
    p = ORIGINALS_ROOT
    for seg in parts:
        p = p.parent if seg == ".." else p / seg
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
        with contextlib.suppress(OSError):
            old.rmdir()
    else:
        import shutil as _sh

        _sh.move(str(old), str(new))


def save_original(folder_path: str, original_name: str, data: bytes | BinaryIO) -> tuple[str, int]:
    """Сохраняет оригинал, возвращает (filename_on_disk, size_bytes).

    Использует open(path, 'xb') для атомарного эксклюзивного создания файла —
    исключает race condition при одновременной загрузке файлов с одинаковым именем.
    """
    safe = sanitize_filename(original_name)
    stem = Path(safe).stem
    ext = Path(safe).suffix.lower() or ".bin"

    target_dir = folder_fs_path(folder_path)
    target_dir.mkdir(parents=True, exist_ok=True)

    fpath: Path | None = None
    out_f = None
    for i in range(10001):
        if i == 0:
            candidate = safe
        elif i <= 9999:
            candidate = f"{stem}-{i}{ext}"
        else:
            candidate = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"

        try:
            p = target_dir / candidate
            out_f = p.open("xb")
            fpath = p
            break
        except FileExistsError:
            continue

    if fpath is None or out_f is None:
        raise OSError(f"Cannot create unique file for '{original_name}' in {target_dir}")

    size = 0
    with out_f:
        if isinstance(data, bytes):
            out_f.write(data)
            size = len(data)
        else:
            while True:
                chunk = data.read(1024 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)
                size += len(chunk)
    return fpath.name, size


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
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    result: dict[int, Path] = {}
    for size in THUMB_SIZES:
        copy = img.copy()
        copy.thumbnail((size, size), Image.Resampling.LANCZOS)
        out_path = out_dir / f"{size}.webp"
        copy.save(out_path, "WEBP", quality=THUMB_QUALITY, method=6)
        result[size] = out_path
        avif_out = out_dir / f"{size}.avif"
        with contextlib.suppress(Exception):
            copy.save(avif_out, "AVIF", quality=THUMB_QUALITY)
    return result


def extract_exif(
    original_path: Path,
    strip_gps: bool = True,
) -> tuple[dict, tuple[int, int] | None, str | None]:
    """Извлекает EXIF, размеры, taken_at (ISO-строка).

    Returns: (exif_dict, (width, height) | None, taken_at_iso | None)
    """
    from PIL import ExifTags  # lazy

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
                with contextlib.suppress(OSError):
                    f.unlink()
            d.rmdir()
    except OSError:
        pass


def thumb_path(photo_id: uuid.UUID, size: int) -> Path:
    if size not in THUMB_SIZES:
        raise ValueError(f"Invalid thumbnail size: {size}")
    return THUMBS_ROOT / str(photo_id) / f"{size}.webp"


def thumb_avif_path(photo_id: uuid.UUID, size: int) -> Path:
    if size not in THUMB_SIZES:
        raise ValueError(f"Invalid thumbnail size: {size}")
    return THUMBS_ROOT / str(photo_id) / f"{size}.avif"
