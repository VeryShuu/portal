"""Хранение файлов фотогалереи (ADR-031).

Структура на диске:
  /data/photos/originals/{folder_path}/{filename}
  /data/photos/thumbs/{photo_id}/{200|600|1600}.webp

Оригиналы помещаются по иерархии папок (зеркало БД). Thumbnails — плоско по ID.

Раньше — монолитный ``app/services/photos_storage.py`` (446 строк). Разложен
на подмодули по ответственности (см. ref.md, пункт 4.1):

- :mod:`.paths` — roots/константы путей, sanitize_*, ``folder_fs_path``,
  ``rename_folder_dir``, ``thumb_path``, ``thumb_avif_path``.
- :mod:`.originals` — ``save_original``, ``delete_photo_files``.
- :mod:`.thumbnails` — ``generate_thumbnails`` (+safe), ``_open_image``,
  локи/семафор, thumb-константы.
- :mod:`.metadata` — ``compute_blurhash``, ``extract_exif``.

Все публичные имена реэкспортированы из пакета — внешние импорты
``from app.services import photos_storage`` + ``photos_storage.X`` остаются
совместимыми. Патчабельные имена (``ORIGINALS_ROOT``, ``THUMBS_ROOT``,
``GENERATE_AVIF``, ``_open_image``, ``generate_thumbnails``, ...) подмодули
читают через lazy lookup ``from app.services import photos_storage as _ps;
_ps.<name>``, чтобы ``patch("app.services.photos_storage.X", ...)`` из тестов
действовал в runtime.
"""

from __future__ import annotations

from .metadata import _GPS_KEYS, compute_blurhash, extract_exif
from .originals import delete_photo_files, save_original
from .paths import (
    _ALLOWED_EXT,
    _ALLOWED_ROOTS,
    _INVALID_FS,
    _SAFE_NAME,
    IMPORT_ROOT,
    ORIGINALS_ROOT,
    THUMBS_ROOT,
    ZIPS_ROOT,
    folder_fs_path,
    is_allowed_ext,
    logger,
    rename_folder_dir,
    sanitize_filename,
    sanitize_folder_name,
    thumb_avif_path,
    thumb_path,
)
from .thumbnails import (
    _MAX_IMAGE_PIXELS,
    _THUMB_GEN_CONCURRENCY,
    _THUMB_GEN_LOCKS,
    _THUMB_GEN_SEMAPHORE,
    AVIF_MIN_SIZE,
    GENERATE_AVIF,
    THUMB_QUALITY,
    THUMB_SIZES,
    WEBP_METHOD,
    _get_thumb_semaphore,
    _open_image,
    generate_thumbnails,
    generate_thumbnails_safe,
)

__all__ = [
    "AVIF_MIN_SIZE",
    "GENERATE_AVIF",
    "IMPORT_ROOT",
    "ORIGINALS_ROOT",
    "THUMBS_ROOT",
    "THUMB_QUALITY",
    "THUMB_SIZES",
    "WEBP_METHOD",
    "ZIPS_ROOT",
    "_ALLOWED_EXT",
    "_ALLOWED_ROOTS",
    "_GPS_KEYS",
    "_INVALID_FS",
    "_MAX_IMAGE_PIXELS",
    "_SAFE_NAME",
    "_THUMB_GEN_CONCURRENCY",
    "_THUMB_GEN_LOCKS",
    "_THUMB_GEN_SEMAPHORE",
    "_get_thumb_semaphore",
    "_open_image",
    "compute_blurhash",
    "delete_photo_files",
    "extract_exif",
    "folder_fs_path",
    "generate_thumbnails",
    "generate_thumbnails_safe",
    "is_allowed_ext",
    "logger",
    "rename_folder_dir",
    "sanitize_filename",
    "sanitize_folder_name",
    "save_original",
    "thumb_avif_path",
    "thumb_path",
]
