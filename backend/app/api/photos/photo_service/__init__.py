"""Photo service: список/перемещение/массовые операции/загрузка фотографий.

Пакет разделён по доменам:
- ``_queries`` — листинги (``list_folder_photos``, ``list_recent_photos``) и статистика
- ``_move`` — синхронное перемещение одного фото (DB + ФС, с rollback)
- ``_bulk`` — массовые операции (delete / move) над набором фото
- ``_upload`` — pipeline загрузки файлов

Все патчабельные имена (``_module_settings``, ``require_folder_permission``,
``resolve_photo_permission``, ``TrashService``, ...) реэкспортированы в
namespace этого пакета, чтобы ``patch.object(photo_service, "X", ...)``
из тестов работал. Подмодули используют lazy lookup
``from app.api.photos import photo_service as _ps; _ps.<name>(...)``,
чтобы патчи действовали в runtime.
"""

from __future__ import annotations

from app.services.audit import make_audit_emitter
from app.services.photos_acl import (
    perm_gte,
    require_folder_permission,
    resolve_folder_permission,
    resolve_folders_permissions_batch,
    resolve_photo_permission,
)
from app.services.photos_trash import TrashService

from .._common import _enqueue_processing, _module_settings, _photo_to_public, logger
from ._bulk import (
    _bulk_delete_photo,
    _bulk_move_photo,
    _load_bulk_target_folder,
    perform_bulk_action,
)
from ._move import (
    _commit_bulk_or_revert_files,
    _move_photo_file_on_disk,
    move_photo_to_folder,
)
from ._queries import get_storage_stats, list_folder_photos, list_recent_photos
from ._upload import (
    _finalize_uploaded_photos,
    _persist_uploaded_photo,
    _pick_unique_filename,
    _rollback_uploaded_files,
    _save_single_upload,
    _stage_upload_on_disk,
    _validate_upload_context,
    perform_upload,
)

_emit_audit = make_audit_emitter("photo")

__all__ = [
    "TrashService",
    "_bulk_delete_photo",
    "_bulk_move_photo",
    "_commit_bulk_or_revert_files",
    "_emit_audit",
    "_enqueue_processing",
    "_finalize_uploaded_photos",
    "_load_bulk_target_folder",
    "_module_settings",
    "_move_photo_file_on_disk",
    "_persist_uploaded_photo",
    "_photo_to_public",
    "_pick_unique_filename",
    "_rollback_uploaded_files",
    "_save_single_upload",
    "_stage_upload_on_disk",
    "_validate_upload_context",
    "get_storage_stats",
    "list_folder_photos",
    "list_recent_photos",
    "logger",
    "move_photo_to_folder",
    "perform_bulk_action",
    "perform_upload",
    "perm_gte",
    "require_folder_permission",
    "resolve_folder_permission",
    "resolve_folders_permissions_batch",
    "resolve_photo_permission",
]
