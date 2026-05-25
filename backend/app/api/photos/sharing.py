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
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_MANAGER, PERM_UPLOADER
from app.core.system_config import load_system_settings
from app.models.photos import (
    Photo,
    PhotoFolder,
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
from app.core.modules_config import load_modules_shared
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
from .public_views import (  # noqa: F401
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
    folder = await db.scalar(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
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
    folder = await db.scalar(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    res = await db.execute(
        select(PhotoFolderShareToken)
        .where(PhotoFolderShareToken.folder_id == folder_id)
        .order_by(PhotoFolderShareToken.created_at.desc())
    )
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
        for tok in res.scalars().all()
    ]


@router.get("/my-shares", response_model=MySharesResponse)
async def get_my_shares(db: DbDep, user: CurrentUser) -> MySharesResponse:
    now = datetime.now(UTC)
    sys_cfg = load_system_settings()
    base = (sys_cfg.portal_base_url or "").rstrip("/")

    res_photo = await db.execute(
        select(PhotoShareToken)
        .where(
            PhotoShareToken.created_by == user.id,
            PhotoShareToken.revoked_at.is_(None),
        )
        .order_by(PhotoShareToken.created_at.desc())
    )
    photo_tokens = [
        PhotoSharePublicForList(
            id=tok.id,
            photo_id=tok.photo_id,
            token=tok.token,
            url=f"{base}/p/{tok.token}",
            created_at=tok.created_at,
            expires_at=tok.expires_at,
        )
        for tok in res_photo.scalars().all()
        if not (tok.expires_at and tok.expires_at < now)
    ]

    res_folder = await db.execute(
        select(PhotoFolderShareToken, PhotoFolder.name)
        .join(PhotoFolder, PhotoFolderShareToken.folder_id == PhotoFolder.id)
        .where(
            PhotoFolderShareToken.created_by == user.id,
            PhotoFolderShareToken.revoked_at.is_(None),
        )
        .order_by(PhotoFolderShareToken.created_at.desc())
    )
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
        for tok, folder_name in res_folder.all()
        if not (tok.expires_at and tok.expires_at < now)
    ]
    return MySharesResponse(photo_tokens=photo_tokens, folder_tokens=folder_tokens)


@router.delete("/my-shares/photo/{token_id}", status_code=204)
async def revoke_photo_share(
    token_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> Response:
    tok = await db.scalar(select(PhotoShareToken).where(PhotoShareToken.id == token_id))
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
    tok = await db.scalar(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.id == token_id)
    )
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
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_UPLOADER, db, redis)
    await _validate_share_ttl(redis, body.expires_in_days)

    token = secrets.token_urlsafe(32)
    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(UTC).replace(microsecond=0) + timedelta(
            days=body.expires_in_days
        )

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
