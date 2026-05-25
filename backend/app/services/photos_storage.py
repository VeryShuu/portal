"""Хранение файлов фотогалереи (ADR-031).

Структура на диске:
  /data/photos/originals/{folder_path}/{filename}
  /data/photos/thumbs/{photo_id}/{200|600|1600}.webp

Оригиналы помещаются по иерархии папок (зеркало БД). Thumbnails — плоско по ID.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any, BinaryIO

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
# WebP encoder method: 0 — самый быстрый, 6 — самый «умный»/медленный.
# Снижено с 6 до 4: разница в размере файла <5%, скорость кодирования выше в 2–3 раза.
WEBP_METHOD = 4
# Опционально генерировать AVIF (дорогой кодек). Можно отключить через
# переменную окружения PHOTOS_GENERATE_AVIF=0, если CPU дорог.
GENERATE_AVIF = os.environ.get("PHOTOS_GENERATE_AVIF", "1") not in ("0", "false", "False", "")
# AVIF дорог; для сеточных миниатюр (200/400/600) выигрыш по размеру не оправдывает
# CPU. Генерируем AVIF только для больших размеров (lightbox/preview).
AVIF_MIN_SIZE = int(os.environ.get("PHOTOS_AVIF_MIN_SIZE", "1000"))

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
            if p.is_relative_to(allowed.resolve()):
                return p
        raise ValueError("Invalid folder path")
    # Относительный путь → ORIGINALS_ROOT, резолвим ".." вручную
    parts = [seg for seg in fs.replace("\\", "/").split("/") if seg and seg != "."]
    p = ORIGINALS_ROOT
    for seg in parts:
        p = p.parent if seg == ".." else p / seg
    p = p.resolve()
    if not p.is_relative_to(ORIGINALS_ROOT.resolve()):
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
    if new.exists():
        raise FileExistsError(f"Destination directory already exists on disk: {new_fs_path}")
    new.parent.mkdir(parents=True, exist_ok=True)
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


_MAX_IMAGE_PIXELS = 300_000_000  # ~300 MP, защита от OOM воркера при обработке гигантских файлов

_THUMB_GEN_LOCKS: dict[str, list] = {}
_THUMB_GEN_SEMAPHORE: asyncio.Semaphore | None = None
_THUMB_GEN_CONCURRENCY = int(os.environ.get("PHOTOS_THUMB_CONCURRENCY", "4"))


def _get_thumb_semaphore() -> asyncio.Semaphore:
    global _THUMB_GEN_SEMAPHORE
    if _THUMB_GEN_SEMAPHORE is None:
        _THUMB_GEN_SEMAPHORE = asyncio.Semaphore(_THUMB_GEN_CONCURRENCY)
    return _THUMB_GEN_SEMAPHORE


async def generate_thumbnails_safe(photo_id: uuid.UUID, original_path: Path) -> dict[int, Path]:
    """Сериализованная on-the-fly генерация thumbnails.

    Защита от OOM при параллельных запросах: per-photo lock (dedupe) +
    глобальный семафор (cap по RAM). Если thumbnails уже сгенерированы
    к моменту попадания внутрь lock — возвращает пустой dict без работы.
    """
    key = str(photo_id)
    lock_info = _THUMB_GEN_LOCKS.get(key)
    if lock_info is None:
        lock = asyncio.Lock()
        _THUMB_GEN_LOCKS[key] = [lock, 1]
    else:
        lock = lock_info[0]
        lock_info[1] += 1

    try:
        async with lock:
            existing = THUMBS_ROOT / key
            if existing.exists() and all(
                (existing / f"{size}.webp").exists() for size in THUMB_SIZES
            ):
                return {}
            sem = _get_thumb_semaphore()
            async with sem:
                return await asyncio.to_thread(generate_thumbnails, photo_id, original_path)
    finally:
        lock_info = _THUMB_GEN_LOCKS.get(key)
        if lock_info is not None:
            lock_info[1] -= 1
            if lock_info[1] <= 0:
                _THUMB_GEN_LOCKS.pop(key, None)


def _open_image(path: Path) -> Any:
    # pillow-heif регистрирует HEIF через register_heif_opener; если не доступен — игнорируем.
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:
        pass
    from PIL import Image  # lazy import
    from PIL.Image import DecompressionBombError

    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS
    img = Image.open(path)
    width, height = img.size
    if width * height > _MAX_IMAGE_PIXELS:
        raise DecompressionBombError(
            f"Image dimensions {width}x{height} exceed the limit of {_MAX_IMAGE_PIXELS} pixels"
        )
    try:
        img.load()
    except DecompressionBombError as e:
        logger.error("photos.decompression_bomb", path=str(path), error=str(e))
        raise
    return img


def compute_blurhash(image_path: Path) -> str | None:
    """Compute a small blurhash string from an existing image (preferably the 200.webp thumb).

    Returns None on any failure (e.g. unsupported format, broken file).
    """
    try:
        import blurhash as _blurhash  # type: ignore
        from PIL import Image  # lazy
    except Exception:
        return None
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            # Downscale further for speed; blurhash precision unaffected.
            img.thumbnail((64, 64), Image.Resampling.LANCZOS)
            return _blurhash.encode(img, x_components=4, y_components=3)
    except Exception:
        return None


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

    # Каскадный downscale: сначала ужимаем оригинал до самого большого размера,
    # затем каждый следующий — из уже уменьшенного. На 5K×3K JPEG это даёт
    # 3–5× прирост скорости по сравнению с resize'ом оригинала на каждый размер.
    result: dict[int, Path] = {}
    sizes_desc = sorted(THUMB_SIZES, reverse=True)
    current = img
    for size in sizes_desc:
        if max(current.size) > size:
            scaled = current.copy()
            scaled.thumbnail((size, size), Image.Resampling.LANCZOS)
        else:
            scaled = current
        out_path = out_dir / f"{size}.webp"
        scaled.save(out_path, "WEBP", quality=THUMB_QUALITY, method=WEBP_METHOD)
        result[size] = out_path
        if GENERATE_AVIF and size >= AVIF_MIN_SIZE:
            avif_out = out_dir / f"{size}.avif"
            with contextlib.suppress(Exception):
                scaled.save(avif_out, "AVIF", quality=THUMB_QUALITY)
        current = scaled
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
