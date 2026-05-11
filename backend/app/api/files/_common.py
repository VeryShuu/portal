"""Shared helpers for the files API package.

Constants, sanitizers, module-enabled guard, folder lookup and
cross-cutting helpers used by multiple submodules.
"""

from __future__ import annotations

import re
import uuid

from fastapi import Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, RedisDep
from app.api.modules import load_modules
from app.core.logging import get_logger
from app.models.files import FileFolder, FileItem
from app.models.user import User
from app.schemas.files import (
    FileFolderPublic,
    NCItem,
    UploadedByPublic,
)
from app.services.files_acl import batch_resolve_folder_permissions, perm_gte

logger = get_logger(__name__)

_SAFE_NAME_RE = re.compile(r'^[^\x00-\x1f\x7f/\\:*?"<>|]{1,200}$')

_PREVIEW_MIME_WHITELIST = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/avif",
        "application/pdf",
    }
)

_BLOCKED_UPLOAD_MIME = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "image/svg+xml",
        "text/javascript",
        "application/javascript",
        "application/x-javascript",
        "application/x-sh",
        "application/x-csh",
        "text/x-shellscript",
        "application/x-executable",
        "application/x-elf",
        "application/x-msdos-program",
        "application/x-msdownload",
        "application/x-dosexec",
        "application/vnd.microsoft.portable-executable",
        "application/x-python-code",
        "text/x-python",
        "application/x-ruby",
        "application/x-php",
        "application/x-httpd-php",
    }
)

# Whitelist разрешённых MIME-типов для загрузки в Nextcloud (#33).
# python-magic возвращает реальный тип файла по содержимому; всё, что не в списке
# и/или попало в _BLOCKED_UPLOAD_MIME — отклоняется.
_UPLOAD_MIME_ALLOWLIST = frozenset(
    {
        # Документы
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation",
        "application/rtf",
        "text/plain",
        "text/csv",
        "text/markdown",
        "application/json",
        "application/xml",
        "text/xml",
        # Изображения
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/avif",
        "image/heif",
        "image/heic",
        "image/bmp",
        "image/tiff",
        # Аудио / видео
        "audio/mpeg",
        "audio/mp4",
        "audio/ogg",
        "audio/wav",
        "audio/x-wav",
        "audio/flac",
        "audio/webm",
        "video/mp4",
        "video/mpeg",
        "video/webm",
        "video/quicktime",
        "video/x-msvideo",
        "video/x-matroska",
        # Архивы
        "application/zip",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
        "application/vnd.rar",
        "application/x-tar",
        "application/gzip",
        "application/x-bzip2",
        "application/x-xz",
    }
)


def sanitize_name(name: str) -> str:
    name = name.strip().strip(".")
    if not name:
        raise HTTPException(status_code=422, detail="Name must not be empty")
    if not _SAFE_NAME_RE.match(name):
        raise HTTPException(
            status_code=422,
            detail=(
                "Name contains invalid characters. "
                'Use printable characters only, no / \\ : * ? " < > |'
            ),
        )
    if name in ("..", "."):
        raise HTTPException(status_code=422, detail="Name must not be '.' or '..'")
    return name


def _check_module_enabled() -> None:
    modules = load_modules()
    if not modules.nextcloud.enabled:
        raise HTTPException(status_code=503, detail="Files module is disabled")


ModuleCheck = Depends(_check_module_enabled)


async def _get_folder_or_404(db: AsyncSession, folder_id: uuid.UUID) -> FileFolder:
    res = await db.execute(
        select(FileFolder).where(FileFolder.id == folder_id, FileFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


async def _folder_to_public(folder: FileFolder, perm: str | None) -> FileFolderPublic:
    return FileFolderPublic(
        id=folder.id,
        parent_id=folder.parent_id,
        name=folder.name,
        nc_path=folder.nc_path,
        description=folder.description,
        permission=perm,
        inherit_permissions=folder.inherit_permissions,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


async def _build_breadcrumbs(
    folder: FileFolder,
    db: AsyncSession,
    user: CurrentUser,  # type: ignore[type-arg]
    redis: RedisDep,  # type: ignore[type-arg]
) -> list[FileFolderPublic]:
    if not folder.parent_id:
        return []

    result = await db.execute(
        text("""
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, name, nc_path, description,
                       inherit_permissions,
                       created_by, created_at, updated_at, deleted_at,
                       1 AS depth
                FROM file_folders
                WHERE id = :start_id AND deleted_at IS NULL
                UNION ALL
                SELECT f.id, f.parent_id, f.name, f.nc_path, f.description,
                       f.inherit_permissions,
                       f.created_by, f.created_at, f.updated_at, f.deleted_at,
                       a.depth + 1
                FROM file_folders f
                JOIN ancestors a ON f.id = a.parent_id
                WHERE a.depth < 20 AND f.deleted_at IS NULL
            )
            SELECT id, parent_id, name, nc_path, description,
                   inherit_permissions,
                   created_by, created_at, updated_at
            FROM ancestors
            ORDER BY depth DESC
        """),
        {"start_id": str(folder.parent_id)},
    )
    rows = result.fetchall()
    if not rows:
        return []

    ancestor_folders = [
        FileFolder(
            id=row[0],
            parent_id=row[1],
            name=row[2],
            nc_path=row[3],
            description=row[4],
            inherit_permissions=row[5],
            created_by=row[6],
            created_at=row[7],
            updated_at=row[8],
        )
        for row in rows
    ]

    perms = await batch_resolve_folder_permissions(user, ancestor_folders, db, redis)
    return [
        await _folder_to_public(f, perms.get(f.id))
        for f in ancestor_folders
    ]


async def _filter_nc_subfolders_by_acl(
    items: list[NCItem],
    parent: FileFolder,
    user: User,
    db: AsyncSession,
    redis: RedisDep,  # type: ignore[type-arg]
) -> list[NCItem]:
    """Hide subfolders the user has no viewer permission on.

    Files inside the parent folder remain visible (they inherit the parent's ACL).
    Subfolders that exist in NC but not in DB are kept (sync gap; treated as
    inheriting the parent's permission, which the caller already validated).
    """
    dir_paths = [item.nc_path for item in items if item.is_dir]
    if not dir_paths:
        return items

    res = await db.execute(
        select(FileFolder).where(
            FileFolder.nc_path.in_(dir_paths),
            FileFolder.deleted_at.is_(None),
        )
    )
    sub_folders = list(res.scalars().all())
    if not sub_folders:
        return items

    perms = await batch_resolve_folder_permissions(user, sub_folders, db, redis)
    perm_by_path: dict[str, str | None] = {f.nc_path: perms.get(f.id) for f in sub_folders}

    filtered: list[NCItem] = []
    for item in items:
        if (
            item.is_dir
            and item.nc_path in perm_by_path
            and not perm_gte(perm_by_path[item.nc_path], "viewer")
        ):
            continue
        filtered.append(item)
    return filtered


async def _enrich_nc_items_with_db(
    items: list[NCItem],
    folder: FileFolder,
    db: AsyncSession,
) -> list[NCItem]:
    """Merge upload metadata from file_items into NCItem list (bulk, no N+1)."""
    file_names = {item.name for item in items if not item.is_dir}
    if not file_names:
        return items

    rows = await db.execute(
        select(FileItem, User)
        .outerjoin(User, FileItem.uploaded_by == User.id)
        .where(
            FileItem.folder_id == folder.id,
            FileItem.name.in_(file_names),
            FileItem.deleted_at.is_(None),
        )
    )
    meta: dict[str, tuple[FileItem, User | None]] = {
        row.FileItem.name: (row.FileItem, row.User) for row in rows
    }

    enriched: list[NCItem] = []
    for item in items:
        if item.is_dir or item.name not in meta:
            enriched.append(item)
            continue
        fi, uploader = meta[item.name]
        uploaded_by = None
        if uploader is not None:
            uploaded_by = UploadedByPublic(
                id=uploader.id,
                full_name=uploader.full_name,
                avatar_url=uploader.avatar_url,
            )
        enriched.append(
            item.model_copy(
                update={"uploaded_at": fi.uploaded_at, "uploaded_by": uploaded_by}
            )
        )
    return enriched
