"""File-level operations: delete + bulk-delete + bulk-move + inflight helpers."""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi_limiter.depends import RateLimiter
from redis.asyncio import Redis
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.constants import BULK_INFLIGHT_TTL as _BULK_INFLIGHT_TTL
from app.models.files import FileItem
from app.schemas.files import (
    BulkDeleteRequest,
    BulkDeleteResult,
    BulkDeleteResultItem,
    BulkMoveRequest,
    BulkMoveResult,
    BulkMoveResultItem,
)
from app.services.audit import push_audit_event
from app.services.files_acl import invalidate_folder_cache, require_folder_permission
from app.services.nextcloud import NextcloudError, get_nc_service

from ._common import ModuleCheck, _get_folder_or_404, logger, sanitize_name
from ._share_drift import move_file_shares, revoke_file_shares

router = APIRouter(tags=["files"])


# ── Delete file ────────────────────────────────────────────────────────────────


@router.delete("/files/file", status_code=204, dependencies=[ModuleCheck])
async def delete_file(
    folder_id: uuid.UUID,
    filename: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> None:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "editor", db, redis)

    safe_filename = sanitize_name(filename)
    nc_path = f"{folder.nc_path}/{safe_filename}"

    nc = get_nc_service()
    try:
        await nc.delete(nc_path)
    except NextcloudError as e:
        if e.status != 404:
            raise HTTPException(status_code=502, detail=str(e)) from e

    fi_res = await db.execute(
        select(FileItem).where(
            FileItem.folder_id == folder.id,
            FileItem.name == safe_filename,
            FileItem.deleted_at.is_(None),
        )
    )
    fi = fi_res.scalar_one_or_none()
    if fi is not None:
        fi.deleted_at = datetime.now(UTC)
        await db.commit()

    await revoke_file_shares(
        db,
        redis,
        folder_id=folder.id,
        filename=safe_filename,
        nc_path=nc_path,
    )

    await push_audit_event(
        redis,
        event_type="files.file_deleted",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="file",
        resource_title=safe_filename,
        metadata={"folder_id": str(folder.id)},
    )


# ── Bulk inflight helpers ──────────────────────────────────────────────────────


def _bulk_inflight_key(user_id: uuid.UUID) -> str:
    return f"bulk:inflight:{user_id}"


async def _try_set_inflight(redis: Redis, user_id: uuid.UUID) -> bool:
    """SETNX with TTL. Returns True if lock acquired, False if already busy."""
    ok = await redis.set(
        _bulk_inflight_key(user_id),
        "1",
        ex=_BULK_INFLIGHT_TTL,
        nx=True,
    )
    return bool(ok)


async def _clear_inflight(redis: Redis, user_id: uuid.UUID) -> None:
    with contextlib.suppress(Exception):
        await redis.delete(_bulk_inflight_key(user_id))


def _validate_bulk_names(
    raw_names: list[str],
) -> tuple[list[str], list[BulkDeleteResultItem]]:
    """Dedup + sanitize. Returns (valid_names, invalid_items)."""
    seen: set[str] = set()
    valid: list[str] = []
    invalid: list[BulkDeleteResultItem] = []
    for raw in raw_names:
        if raw in seen:
            continue
        seen.add(raw)
        try:
            name = sanitize_name(raw.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
        except HTTPException:
            invalid.append(BulkDeleteResultItem(name=raw, success=False, error="invalid_name"))
            continue
        valid.append(name)
    return valid, invalid


# ── Bulk delete ────────────────────────────────────────────────────────────────


@router.post(
    "/files/folders/{folder_id}/bulk-delete",
    response_model=BulkDeleteResult,
    dependencies=[ModuleCheck, Depends(RateLimiter(times=3, minutes=1))],
)
async def bulk_delete_files(
    folder_id: uuid.UUID,
    body: BulkDeleteRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> BulkDeleteResult:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "editor", db, redis)

    if not await _try_set_inflight(redis, user.id):
        raise HTTPException(status_code=409, detail="bulk_in_progress")

    try:
        valid_names, failed = _validate_bulk_names(body.filenames)

        deleted: list[BulkDeleteResultItem] = []
        nc_404_count = 0
        names_for_db: list[str] = []
        nc = get_nc_service()

        for name in valid_names:
            nc_path = f"{folder.nc_path}/{name}"
            try:
                await nc.delete(nc_path)
                deleted.append(BulkDeleteResultItem(name=name, success=True))
                names_for_db.append(name)
            except NextcloudError as e:
                if e.status == 404:
                    nc_404_count += 1
                    deleted.append(BulkDeleteResultItem(name=name, success=True))
                    names_for_db.append(name)
                else:
                    failed.append(
                        BulkDeleteResultItem(
                            name=name,
                            success=False,
                            error=f"nc_error:{e.status}",
                        )
                    )

        if names_for_db:
            now = datetime.now(UTC)
            fi_res = await db.execute(
                select(FileItem).where(
                    FileItem.folder_id == folder.id,
                    FileItem.name.in_(names_for_db),
                    FileItem.deleted_at.is_(None),
                )
            )
            db_commit_failed = False
            for fi in fi_res.scalars().all():
                fi.deleted_at = now
            try:
                await db.commit()
            except Exception as exc:
                logger.error(
                    "files.bulk_delete_db_commit_failed",
                    folder_id=str(folder.id),
                    error=str(exc),
                )
                db_commit_failed = True
                await db.rollback()

            await invalidate_folder_cache(redis, folder.id, db)
            for name in names_for_db:
                await revoke_file_shares(
                    db,
                    redis,
                    folder_id=folder.id,
                    filename=name,
                    nc_path=f"{folder.nc_path}/{name}",
                )
            await push_audit_event(
                redis,
                event_type="files.bulk_deleted",
                user_id=str(user.id),
                user_email=user.email,
                resource_type="folder",
                resource_id=str(folder.id),
                metadata={
                    "folder_id": str(folder.id),
                    "count_total": len(body.filenames),
                    "count_deleted": len(deleted),
                    "count_failed": len(failed),
                    "nc_404_count": nc_404_count,
                    "db_commit_failed": db_commit_failed,
                },
            )
        else:
            await push_audit_event(
                redis,
                event_type="files.bulk_deleted",
                user_id=str(user.id),
                user_email=user.email,
                resource_type="folder",
                resource_id=str(folder.id),
                metadata={
                    "folder_id": str(folder.id),
                    "count_total": len(body.filenames),
                    "count_deleted": 0,
                    "count_failed": len(failed),
                    "nc_404_count": 0,
                    "db_commit_failed": False,
                },
            )

        return BulkDeleteResult(deleted=deleted, failed=failed)
    finally:
        await _clear_inflight(redis, user.id)


# ── Bulk move ──────────────────────────────────────────────────────────────────


@router.post(
    "/files/folders/{folder_id}/bulk-move",
    response_model=BulkMoveResult,
    dependencies=[ModuleCheck, Depends(RateLimiter(times=3, minutes=1))],
)
async def bulk_move_files(
    folder_id: uuid.UUID,
    body: BulkMoveRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> BulkMoveResult:
    if body.target_folder_id == folder_id:
        raise HTTPException(status_code=422, detail="same_folder")

    src_folder = await _get_folder_or_404(db, folder_id)
    target_folder = await _get_folder_or_404(db, body.target_folder_id)
    await require_folder_permission(user, src_folder, "editor", db, redis)
    await require_folder_permission(user, target_folder, "editor", db, redis)

    settings = get_settings()
    nc_root = getattr(settings, "nc_files_root", None) or "PortalFiles"
    if not target_folder.nc_path.startswith(nc_root):
        raise HTTPException(status_code=500, detail="target_outside_root")

    if not await _try_set_inflight(redis, user.id):
        raise HTTPException(status_code=409, detail="bulk_in_progress")

    try:
        valid_names, invalid_items = _validate_bulk_names(body.filenames)
        failed: list[BulkMoveResultItem] = [
            BulkMoveResultItem(name=i.name, success=False, error=i.error) for i in invalid_items
        ]
        moved: list[BulkMoveResultItem] = []
        drift_count = 0
        nc = get_nc_service()

        for name in valid_names:
            src_path = f"{src_folder.nc_path}/{name}"
            dst_path = f"{target_folder.nc_path}/{name}"
            try:
                await nc.move(src_path, dst_path)
            except NextcloudError as e:
                if e.status == 412:
                    failed.append(
                        BulkMoveResultItem(name=name, success=False, error="name_conflict")
                    )
                elif e.status == 404:
                    failed.append(BulkMoveResultItem(name=name, success=False, error="not_found"))
                else:
                    failed.append(
                        BulkMoveResultItem(name=name, success=False, error=f"nc_error:{e.status}")
                    )
                continue

            try:
                fi_res = await db.execute(
                    select(FileItem).where(
                        FileItem.folder_id == src_folder.id,
                        FileItem.name == name,
                        FileItem.deleted_at.is_(None),
                    )
                )
                fi = fi_res.scalar_one_or_none()
                if fi is not None:
                    fi.folder_id = target_folder.id
                    fi.nc_path = dst_path
                else:
                    db.add(
                        FileItem(
                            folder_id=target_folder.id,
                            nc_path=dst_path,
                            name=name,
                            size_bytes=0,
                            mime_type=None,
                            uploaded_by=None,
                            uploaded_at=datetime.now(UTC),
                        )
                    )
                await db.commit()
                await move_file_shares(
                    db,
                    redis,
                    src_folder_id=src_folder.id,
                    src_filename=name,
                    src_nc_path=src_path,
                    dst_folder_id=target_folder.id,
                    dst_filename=name,
                    dst_nc_path=dst_path,
                )
                moved.append(BulkMoveResultItem(name=name, success=True))
            except Exception as exc:
                await db.rollback()
                drift_count += 1
                logger.warning(
                    "files.bulk_move_drift",
                    nc_path_src=src_path,
                    nc_path_dst=dst_path,
                    error=str(exc),
                )
                await push_audit_event(
                    redis,
                    event_type="files.bulk_move_drift",
                    user_id=str(user.id),
                    user_email=user.email,
                    resource_type="file",
                    resource_title=name,
                    metadata={
                        "src_folder_id": str(src_folder.id),
                        "target_folder_id": str(target_folder.id),
                        "nc_path_src": src_path,
                        "nc_path_dst": dst_path,
                    },
                )
                # NC уже переместил — для пользователя это успех; дрейф фиксится sync'ом.
                moved.append(BulkMoveResultItem(name=name, success=True))

        await invalidate_folder_cache(redis, src_folder.id, db)
        await invalidate_folder_cache(redis, target_folder.id, db)
        await push_audit_event(
            redis,
            event_type="files.bulk_moved",
            user_id=str(user.id),
            user_email=user.email,
            resource_type="folder",
            resource_id=str(src_folder.id),
            metadata={
                "src_folder_id": str(src_folder.id),
                "target_folder_id": str(target_folder.id),
                "count_total": len(body.filenames),
                "count_moved": len(moved),
                "count_failed": len(failed),
                "count_drift": drift_count,
            },
        )

        return BulkMoveResult(moved=moved, failed=failed)
    finally:
        await _clear_inflight(redis, user.id)
