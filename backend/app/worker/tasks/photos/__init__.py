"""ARQ задачи модуля фотогалереи.

Раньше — монолитный ``app/worker/tasks/photos.py`` (524 строки). Разложен
на подмодули по ответственности (см. ref.md, пункт 3.1):

- :mod:`.processing` — ``process_photo_upload``, ``detect_missing_thumbnails``.
- :mod:`.cleanup` — ``cleanup_deleted_photos``, ``cleanup_zip_jobs``,
  ``empty_photo_trash``.
- :mod:`.zip_jobs` — ``generate_folder_zip``.
- :mod:`.import_scan` — сканирование ``/import`` директории.

Все функции реэкспортированы из пакета — внешние импорты вида
``from app.worker.tasks.photos import process_photo_upload`` продолжают работать.
"""

from __future__ import annotations

from app.services import photos_storage

from .cleanup import (
    _TRASH_EMPTY_LOCK_KEY,
    cleanup_deleted_photos,
    cleanup_zip_jobs,
    empty_photo_trash,
)
from .import_scan import (
    _IMPORT_BATCH_SIZE,
    _IMPORT_FILE_LIMIT,
    _slugify_import,
    import_scan_run,
)
from .processing import detect_missing_thumbnails, process_photo_upload
from .zip_jobs import generate_folder_zip

__all__ = [
    "_IMPORT_BATCH_SIZE",
    "_IMPORT_FILE_LIMIT",
    "_TRASH_EMPTY_LOCK_KEY",
    "_slugify_import",
    "cleanup_deleted_photos",
    "cleanup_zip_jobs",
    "detect_missing_thumbnails",
    "empty_photo_trash",
    "generate_folder_zip",
    "import_scan_run",
    "photos_storage",
    "process_photo_upload",
]
