"""Управление share-токенами (создание / просмотр / отзыв).

Публичные read-only эндпойнты вынесены в :mod:`public_views`
(см. ревью, находка #4).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_MANAGER, PERM_UPLOADER
from app.core.modules_config import load_modules_shared
from app.core.system_config import load_system_settings
from app.models.photos import (
    PhotoFolderShareToken,
    PhotoShareToken,
)
from app.schemas.photos import (
    FolderShareLinkPublic,
    FolderShareLinkRequest,
    FolderSharePublicForList,
    MySharesResponse,
    PhotoSharePublicForList,
    ShareLinkPublic,
    ShareLinkRequest,
)
from app.services import photos_photo_repo, photos_share_repo
from app.services.audit import push_audit_event
from app.services.photos_acl import require_folder_permission, require_photo_permission


async def _validate_share_ttl(redis: RedisDep, requested_days: int | None) -> None:
    """#B-10: проверяет TTL share-ссылки против runtime-капы из module_settings.

    Возвращает None, если ``requested_days`` укладывается в
    ``photos.max_share_ttl_days`` (или TTL не задан). Иначе HTTP 400.
    """
    if requested_days is None:
        return
    modules = await load_modules_shared(redis)
    cap = modules.photos.max_share_ttl_days
    if requested_days > cap:
        raise HTTPException(
            status_code=400,
            detail=f"Share TTL exceeds allowed maximum of {cap} days",
        )


# Re-export для обратной совместимости с тестами (tests/unit/test_photos_sharing.py).
from .public_views import (  # noqa: F401, E402
    _resolve_folder_token_sync_check,
    _resolve_token,
)

router = APIRouter()


@router.post("/folders/{folder_id}/share", response_model=FolderShareLinkPublic, status_code=201)
async def create_folder_share(
    folder_id: uuid.UUID,
    data: FolderShareLinkRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> FolderShareLinkPublic:
    folder = await photos_photo_repo.scalar_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    await _validate_share_ttl(redis, data.expires_in_days)
    token_str = secrets.token_urlsafe(32)
    expires_at = (
        datetime.now(UTC) + timedelta(days=data.expires_in_days) if data.expires_in_days else None
    )
    tok = PhotoFolderShareToken(
        folder_id=folder_id, token=token_str, created_by=user.id, expires_at=expires_at
    )
    db.add(tok)
    await db.commit()
    await db.refresh(tok)
    await push_audit_event(
        redis,
        event_type="photos.folder_share_created",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo_folder",
        resource_id=str(folder_id),
    )
    sys_cfg = load_system_settings()
    base = (sys_cfg.portal_base_url or "").rstrip("/")
    url = f"{base}/photos/public/{token_str}"
    return FolderShareLinkPublic(
        id=tok.id,
        folder_id=tok.folder_id,
        token=tok.token,
        url=url,
        created_at=tok.created_at,
        expires_at=tok.expires_at,
    )


@router.get("/folders/{folder_id}/shares", response_model=list[FolderShareLinkPublic])
async def list_folder_shares(
    folder_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> list[FolderShareLinkPublic]:
    folder = await photos_photo_repo.scalar_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    tokens = await photos_share_repo.list_folder_share_tokens(db, folder_id)
    sys_cfg = load_system_settings()
    base = (sys_cfg.portal_base_url or "").rstrip("/")
    return [
        FolderShareLinkPublic(
            id=tok.id,
            folder_id=tok.folder_id,
            token=tok.token,
            url=f"{base}/photos/public/{tok.token}",
            created_at=tok.created_at,
            expires_at=tok.expires_at,
        )
        for tok in tokens
    ]


@router.get("/my-shares", response_model=MySharesResponse)
async def get_my_shares(db: DbDep, user: CurrentUser) -> MySharesResponse:
    now = datetime.now(UTC)
    sys_cfg = load_system_settings()
    base = (sys_cfg.portal_base_url or "").rstrip("/")

    photo_share_tokens = await photos_share_repo.list_my_photo_shares(db, user.id)
    photo_tokens = [
        PhotoSharePublicForList(
            id=tok.id,
            photo_id=tok.photo_id,
            token=tok.token,
            url=f"{base}/p/{tok.token}",
            created_at=tok.created_at,
            expires_at=tok.expires_at,
        )
        for tok in photo_share_tokens
        if not (tok.expires_at and tok.expires_at < now)
    ]

    folder_share_rows = await photos_share_repo.list_my_folder_shares(db, user.id)
    folder_tokens = [
        FolderSharePublicForList(
            id=tok.id,
            folder_id=tok.folder_id,
            token=tok.token,
            url=f"{base}/photos/public/{tok.token}",
            folder_name=folder_name,
            created_at=tok.created_at,
            expires_at=tok.expires_at,
        )
        for tok, folder_name in folder_share_rows
        if not (tok.expires_at and tok.expires_at < now)
    ]
    return MySharesResponse(photo_tokens=photo_tokens, folder_tokens=folder_tokens)


@router.delete("/my-shares/photo/{token_id}", status_code=204)
async def revoke_photo_share(
    token_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    tok = await photos_share_repo.get_photo_share_token(db, token_id)
    if not tok:
        raise HTTPException(status_code=404, detail="Token not found")
    if tok.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    tok.revoked_at = datetime.now(UTC)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="photos.share_revoked",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo_share_token",
        resource_id=str(token_id),
    )
    return Response(status_code=204)


@router.delete("/my-shares/folder/{token_id}", status_code=204)
async def revoke_folder_share(
    token_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    tok = await photos_share_repo.get_folder_share_token(db, token_id)
    if not tok:
        raise HTTPException(status_code=404, detail="Token not found")
    if tok.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    tok.revoked_at = datetime.now(UTC)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="photos.folder_share_revoked",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="folder_share_token",
        resource_id=str(token_id),
    )
    return Response(status_code=204)


@router.post("/{photo_id}/share", response_model=ShareLinkPublic, status_code=201)
async def create_share_link(
    photo_id: uuid.UUID,
    request: Request,
    body: ShareLinkRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> ShareLinkPublic:
    photo = await photos_photo_repo.fetch_active_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_UPLOADER, db, redis)
    await _validate_share_ttl(redis, body.expires_in_days)

    token = secrets.token_urlsafe(32)
    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(UTC).replace(microsecond=0) + timedelta(days=body.expires_in_days)

    link = PhotoShareToken(
        photo_id=photo_id,
        token=token,
        created_by=user.id,
        expires_at=expires_at,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    sys_cfg = load_system_settings()
    base = sys_cfg.portal_base_url or str(request.base_url).rstrip("/")
    public_url = f"{base}/p/{token}"

    await push_audit_event(
        redis,
        event_type="photos.share_created",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo",
        resource_id=str(photo_id),
        metadata={
            "token_id": str(link.id),
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )

    return ShareLinkPublic(
        id=link.id,
        photo_id=link.photo_id,
        token=link.token,
        url=public_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
    )
