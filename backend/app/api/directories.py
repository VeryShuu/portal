"""Object directories API (docs/wip/directories.md).

Two-level gating:

* the master ``modules.json`` flag (``directories.enabled``) — when off the
  whole section returns 404 (handled by :func:`require_directories_enabled`);
* a per-type ``enabled`` flag — a disabled type's tab is hidden for regular
  users but stays visible/manageable for editors/admins.

Read access: any authenticated user. Mutations (types, entries, contacts,
avatars): ``editor``/``admin`` via :data:`EditorDep`. Every mutation emits an
audit event after commit.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, UploadFile, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbDep, EditorDep, RedisDep
from app.core.logging import get_logger
from app.core.modules_config import load_modules_shared
from app.core.pdf import render_pdf
from app.models.object_directory import ObjectDirectory
from app.models.user import User
from app.schemas.object_directory import (
    CreateDirectoryRequest,
    CreateEntryRequest,
    DirectoryList,
    DirectoryPublic,
    EntryList,
    EntryPublic,
    UpdateDirectoryRequest,
    UpdateEntryRequest,
)
from app.services import directories as svc
from app.services.audit import make_audit_emitter
from app.services.directory_avatar import remove_avatar_files, save_avatar

router = APIRouter(prefix="/directories", tags=["directories"])
logger = get_logger(__name__)

_emit_audit = make_audit_emitter("directory")

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _require_module_enabled(redis: RedisDep) -> None:
    """404 the whole feature when the master ``directories`` flag is off."""
    modules = await load_modules_shared(redis)
    if not modules.directories.enabled:
        raise _not_found()


def _not_found() -> Exception:
    from fastapi import HTTPException

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Directories disabled")


def _is_editor(user: User) -> bool:
    return user.role in ("editor", "admin")


# ── Directory types ────────────────────────────────────────────────────────────


@router.get("", response_model=DirectoryList, summary="Список типов справочников (вкладок)")
async def list_directories(
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> DirectoryList:
    await _require_module_enabled(redis)
    items, total = await svc.list_directories(db, include_disabled=_is_editor(user))
    return DirectoryList(
        items=[DirectoryPublic.model_validate(d) for d in items],
        total=total,
    )


@router.post(
    "",
    response_model=DirectoryPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Создать тип справочника (editor)",
)
async def create_directory(
    body: CreateDirectoryRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> DirectoryPublic:
    await _require_module_enabled(redis)
    directory = await svc.create_directory(db, body)
    await _emit_audit(
        redis,
        event_type="directories.type_created",
        user_id=str(editor.id),
        resource_id=str(directory.id),
        resource_title=directory.label_ru,
    )
    logger.info("directory.type_created", directory_id=str(directory.id), editor=str(editor.id))
    return DirectoryPublic.model_validate(directory)


@router.patch(
    "/{directory_id}",
    response_model=DirectoryPublic,
    summary="Обновить тип справочника (editor)",
)
async def update_directory(
    directory_id: uuid.UUID,
    body: UpdateDirectoryRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> DirectoryPublic:
    await _require_module_enabled(redis)
    directory = await svc.get_directory_or_404(db, directory_id)
    changed = await svc.update_directory(db, directory, body)
    await _emit_audit(
        redis,
        event_type="directories.type_updated",
        user_id=str(editor.id),
        resource_id=str(directory.id),
        resource_title=directory.label_ru,
        metadata={"fields": changed},
    )
    logger.info("directory.type_updated", directory_id=str(directory.id), editor=str(editor.id))
    return DirectoryPublic.model_validate(directory)


@router.delete(
    "/{directory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить тип справочника (editor, soft)",
)
async def delete_directory(
    directory_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    await _require_module_enabled(redis)
    directory = await svc.get_directory_or_404(db, directory_id)
    await svc.delete_directory(db, directory)
    await _emit_audit(
        redis,
        event_type="directories.type_deleted",
        user_id=str(editor.id),
        resource_id=str(directory_id),
        resource_title=directory.label_ru,
    )
    logger.info("directory.type_deleted", directory_id=str(directory_id), editor=str(editor.id))


# ── Entries ────────────────────────────────────────────────────────────────────


async def _resolve_directory(
    db: DbDep, redis: RedisDep, slug: str, *, user: User
) -> ObjectDirectory:
    await _require_module_enabled(redis)
    directory = await svc.get_directory_by_slug_or_404(db, slug)
    if not directory.enabled and not _is_editor(user):
        raise _not_found()
    return directory


@router.get(
    "/{slug}/entries",
    response_model=EntryList,
    summary="Список объектов справочника",
)
async def list_entries(
    slug: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> EntryList:
    directory = await _resolve_directory(db, redis, slug, user=user)
    items, total = await svc.list_entries(
        db, directory_id=directory.id, q=q, limit=limit, offset=offset
    )
    return EntryList(
        items=[EntryPublic.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{slug}/entries/{entry_id}",
    response_model=EntryPublic,
    summary="Получить объект с контактами",
)
async def get_entry(
    slug: str,
    entry_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> EntryPublic:
    directory = await _resolve_directory(db, redis, slug, user=user)
    entry = await svc.get_entry_or_404(db, directory_id=directory.id, entry_id=entry_id)
    return EntryPublic.model_validate(entry)


@router.post(
    "/{slug}/entries",
    response_model=EntryPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Создать объект (editor)",
)
async def create_entry(
    slug: str,
    body: CreateEntryRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> EntryPublic:
    directory = await _resolve_directory(db, redis, slug, user=editor)
    entry = await svc.create_entry(db, directory=directory, body=body, created_by=editor.id)
    await _emit_audit(
        redis,
        event_type="directories.entry_created",
        user_id=str(editor.id),
        resource_id=str(entry.id),
        resource_title=entry.name,
        metadata={"directory": slug},
    )
    logger.info("directory.entry_created", entry_id=str(entry.id), editor=str(editor.id))
    return EntryPublic.model_validate(entry)


@router.patch(
    "/{slug}/entries/{entry_id}",
    response_model=EntryPublic,
    summary="Обновить объект (editor)",
)
async def update_entry(
    slug: str,
    entry_id: uuid.UUID,
    body: UpdateEntryRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> EntryPublic:
    directory = await _resolve_directory(db, redis, slug, user=editor)
    entry = await svc.get_entry_or_404(db, directory_id=directory.id, entry_id=entry_id)
    refreshed, changed = await svc.update_entry(db, directory=directory, entry=entry, body=body)
    await _emit_audit(
        redis,
        event_type="directories.entry_updated",
        user_id=str(editor.id),
        resource_id=str(entry_id),
        resource_title=refreshed.name,
        metadata={"directory": slug, "fields": changed},
    )
    logger.info("directory.entry_updated", entry_id=str(entry_id), editor=str(editor.id))
    return EntryPublic.model_validate(refreshed)


@router.delete(
    "/{slug}/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить объект (editor, soft)",
)
async def delete_entry(
    slug: str,
    entry_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    directory = await _resolve_directory(db, redis, slug, user=editor)
    entry = await svc.get_entry_or_404(db, directory_id=directory.id, entry_id=entry_id)
    await svc.soft_delete_entry(db, entry)
    remove_avatar_files(entry.id)
    await _emit_audit(
        redis,
        event_type="directories.entry_deleted",
        user_id=str(editor.id),
        resource_id=str(entry_id),
        resource_title=entry.name,
        metadata={"directory": slug},
    )
    logger.info("directory.entry_deleted", entry_id=str(entry_id), editor=str(editor.id))


@router.post(
    "/{slug}/entries/{entry_id}/avatar",
    response_model=EntryPublic,
    summary="Загрузить аватар объекта (editor)",
)
async def upload_entry_avatar(
    slug: str,
    entry_id: uuid.UUID,
    file: UploadFile,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> EntryPublic:
    directory = await _resolve_directory(db, redis, slug, user=editor)
    entry = await svc.get_entry_or_404(db, directory_id=directory.id, entry_id=entry_id)
    avatar_url = await save_avatar(file, entry.id)
    await svc.set_entry_avatar(db, entry, avatar_url)
    refreshed = await svc.get_entry_or_404(db, directory_id=directory.id, entry_id=entry_id)
    await _emit_audit(
        redis,
        event_type="directories.entry_updated",
        user_id=str(editor.id),
        resource_id=str(entry_id),
        resource_title=refreshed.name,
        metadata={"directory": slug, "fields": ["avatar_path"]},
    )
    logger.info("directory.entry_avatar_uploaded", entry_id=str(entry_id), editor=str(editor.id))
    return EntryPublic.model_validate(refreshed)


@router.delete(
    "/{slug}/entries/{entry_id}/avatar",
    response_model=EntryPublic,
    summary="Удалить аватар объекта (editor)",
)
async def delete_entry_avatar(
    slug: str,
    entry_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> EntryPublic:
    directory = await _resolve_directory(db, redis, slug, user=editor)
    entry = await svc.get_entry_or_404(db, directory_id=directory.id, entry_id=entry_id)
    remove_avatar_files(entry.id)
    await svc.set_entry_avatar(db, entry, None)
    refreshed = await svc.get_entry_or_404(db, directory_id=directory.id, entry_id=entry_id)
    await _emit_audit(
        redis,
        event_type="directories.entry_updated",
        user_id=str(editor.id),
        resource_id=str(entry_id),
        resource_title=refreshed.name,
        metadata={"directory": slug, "fields": ["avatar_path"]},
    )
    logger.info("directory.entry_avatar_deleted", entry_id=str(entry_id), editor=str(editor.id))
    return EntryPublic.model_validate(refreshed)


# ── Export ─────────────────────────────────────────────────────────────────────


@router.get(
    "/{slug}/export",
    summary="Экспорт объектов (csv | xlsx | pdf)",
)
async def export_entries(
    slug: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    fmt: str = Query(default="csv", alias="format", pattern="^(csv|xlsx|pdf)$"),
) -> Response:
    directory = await _resolve_directory(db, redis, slug, user=user)
    entries, _ = await svc.list_entries(
        db, directory_id=directory.id, q=None, limit=10000, offset=0
    )

    if fmt == "csv":
        content = svc.build_csv(directory, entries)
        media_type = "text/csv; charset=utf-8"
        filename = svc.export_filename(directory, "csv")
    elif fmt == "xlsx":
        content = svc.build_xlsx(directory, entries)
        media_type = _XLSX_MIME
        filename = svc.export_filename(directory, "xlsx")
    else:
        html = svc.build_export_html(directory, entries)
        content = await render_pdf(html)
        media_type = "application/pdf"
        filename = svc.export_filename(directory, "pdf")

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, max-age=0",
        },
    )
