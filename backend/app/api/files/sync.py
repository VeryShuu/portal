"""Import folder tree from Nextcloud."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbDep, RedisDep, require_role
from app.api.files import repo
from app.services.audit import make_audit_emitter
from app.services.files_acl_persistence import get_folder_perms
from app.services.nextcloud import NextcloudError, get_nc_service

from ._common import ModuleCheck

_emit_audit = make_audit_emitter("folder")

router = APIRouter(tags=["files"])


class NcSyncReport(BaseModel):
    created: int
    skipped: int
    errors: list[str]


@router.post(
    "/files/sync",
    response_model=NcSyncReport,
    dependencies=[ModuleCheck, Depends(require_role("admin"))],
)
async def sync_folders_from_nextcloud(
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> NcSyncReport:
    """Import folder tree from Nextcloud into the portal DB.

    Idempotent: folders already present (by nc_path) are skipped.
    Soft-deleted folders are NOT restored — they are counted as skipped.
    Permissions are restored from files-acl.json backup if available.
    """
    nc = get_nc_service()

    try:
        nc_paths = await nc.list_folders_recursive(max_depth=30)
    except NextcloudError as e:
        raise HTTPException(status_code=502, detail=f"Nextcloud error: {e}") from e

    if not nc_paths:
        return NcSyncReport(created=0, skipped=0, errors=[])

    rows = await repo.list_folder_path_id_pairs(db)
    existing: dict[str, uuid.UUID] = {row.nc_path: row.id for row in rows}

    path_to_id: dict[str, uuid.UUID] = dict(existing)

    created = 0
    skipped = 0
    perms_restored = 0
    now = datetime.now(UTC)

    for nc_path in nc_paths:
        if nc_path in path_to_id:
            skipped += 1
            continue

        name = nc_path.rsplit("/", 1)[-1] if "/" in nc_path else nc_path
        parent_nc_path = nc_path.rsplit("/", 1)[0] if "/" in nc_path else None
        parent_id: uuid.UUID | None = path_to_id.get(parent_nc_path) if parent_nc_path else None

        new_id = uuid.uuid4()
        rowcount = await repo.insert_folder_if_absent(
            db,
            new_id=new_id,
            parent_id=parent_id,
            name=name,
            nc_path=nc_path,
            created_by=user.id,
            now=now,
        )
        if rowcount:
            path_to_id[nc_path] = new_id
            created += 1

            backed_up = get_folder_perms(nc_path)
            for entry in backed_up:
                await repo.insert_folder_permission_if_absent(
                    db,
                    folder_id=new_id,
                    subject_type=entry["subject_type"],
                    subject_id=entry["subject_id"],
                    subject_name=entry["subject_name"],
                    permission=entry["permission"],
                    granted_by=user.id,
                    now=now,
                )
                perms_restored += 1
        else:
            skipped += 1

    await db.commit()

    await _emit_audit(
        redis,
        event_type="files.sync_from_nc",
        user_id=str(user.id),
        user_email=user.email,
        metadata={"created": created, "skipped": skipped, "perms_restored": perms_restored},
    )

    return NcSyncReport(created=created, skipped=skipped, errors=[])
