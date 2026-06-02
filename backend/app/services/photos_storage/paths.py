"""Пути, санитизация имён и резолв директорий фотогалереи.

Часть пакета :mod:`app.services.photos_storage` (см. его ``__init__``).

Патчабельные имена (``ORIGINALS_ROOT``, ``_ALLOWED_ROOTS``, ``THUMBS_ROOT``,
``THUMB_SIZES``, ``folder_fs_path``) читаются через namespace пакета
(``from app.services import photos_storage as _ps``), чтобы
``patch("app.services.photos_storage.X", ...)`` из тестов действовал в runtime.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

ORIGINALS_ROOT = Path("/data/photos/originals")
THUMBS_ROOT = Path("/data/photos/thumbs")
IMPORT_ROOT = Path("/data/photos/import")
ZIPS_ROOT = Path("/data/photos/zips")

# Разрешённые корневые директории для path-validation
_ALLOWED_ROOTS = (ORIGINALS_ROOT, IMPORT_ROOT, ZIPS_ROOT)

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".tif", ".tiff"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


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
    from app.services import photos_storage as _ps

    fs = folder_fs_path_str or ""
    if Path(fs).is_absolute() or fs.startswith("/"):
        # Абсолютный путь — проверяем что он внутри одного из разрешённых корней
        p = Path(fs).resolve()
        for allowed in _ps._ALLOWED_ROOTS:
            if p.is_relative_to(allowed.resolve()):
                return p
        raise ValueError("Invalid folder path")
    # Относительный путь → ORIGINALS_ROOT, резолвим ".." вручную
    parts = [seg for seg in fs.replace("\\", "/").split("/") if seg and seg != "."]
    p = _ps.ORIGINALS_ROOT
    for seg in parts:
        p = p.parent if seg == ".." else p / seg
    p = p.resolve()
    if not p.is_relative_to(_ps.ORIGINALS_ROOT.resolve()):
        raise ValueError("Invalid folder path")
    return p


def rename_folder_dir(old_fs_path: str, new_fs_path: str) -> None:
    """Переименовать каталог на диске при изменении имени/перемещении папки."""
    from app.services import photos_storage as _ps

    if not old_fs_path or old_fs_path == new_fs_path:
        return
    old = _ps.folder_fs_path(old_fs_path)
    new = _ps.folder_fs_path(new_fs_path)
    if not old.exists():
        return
    if new.exists():
        raise FileExistsError(f"Destination directory already exists on disk: {new_fs_path}")
    new.parent.mkdir(parents=True, exist_ok=True)
    import shutil as _sh

    _sh.move(str(old), str(new))


def thumb_path(photo_id: uuid.UUID, size: int) -> Path:
    from app.services import photos_storage as _ps

    if size not in _ps.THUMB_SIZES:
        raise ValueError(f"Invalid thumbnail size: {size}")
    return _ps.THUMBS_ROOT / str(photo_id) / f"{size}.webp"


def thumb_avif_path(photo_id: uuid.UUID, size: int) -> Path:
    from app.services import photos_storage as _ps

    if size not in _ps.THUMB_SIZES:
        raise ValueError(f"Invalid thumbnail size: {size}")
    return _ps.THUMBS_ROOT / str(photo_id) / f"{size}.avif"
