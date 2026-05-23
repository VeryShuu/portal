"""Share tokens (folder + photo) and public endpoints."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    PhotoListAnon,
    PhotoPublicAnon,
    PhotoSharePublicForList,
    ShareLinkPublic,
    ShareLinkRequest,
)
from app.services import photos_storage
from app.services.audit import push_audit_event
from app.services.photos_acl import require_folder_permission, require_photo_permission

from ._common import _photo_to_public_anon

router = APIRouter()


def _resolve_folder_token_sync_check(token_row: PhotoFolderShareToken) -> None:
    now = datetime.now(UTC)
    if token_row.revoked_at is not None or (
        token_row.expires_at is not None and token_row.expires_at < now
    ):
        raise HTTPException(status_code=410, detail="Share link expired or revoked")


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
    result = []
    for tok in res.scalars().all():
        result.append(
            FolderShareLinkPublic(
                id=tok.id,
                folder_id=tok.folder_id,
                token=tok.token,
                url=f"{base}/photos/public/{tok.token}",
                created_at=tok.created_at,
                expires_at=tok.expires_at,
            )
        )
    return result


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
    photo_tokens = []
    for tok in res_photo.scalars().all():
        if tok.expires_at and tok.expires_at < now:
            continue
        photo_tokens.append(
            PhotoSharePublicForList(
                id=tok.id,
                photo_id=tok.photo_id,
                token=tok.token,
                url=f"{base}/p/{tok.token}",
                created_at=tok.created_at,
                expires_at=tok.expires_at,
            )
        )
    res_folder = await db.execute(
        select(PhotoFolderShareToken, PhotoFolder.name)
        .join(PhotoFolder, PhotoFolderShareToken.folder_id == PhotoFolder.id)
        .where(
            PhotoFolderShareToken.created_by == user.id,
            PhotoFolderShareToken.revoked_at.is_(None),
        )
        .order_by(PhotoFolderShareToken.created_at.desc())
    )
    folder_tokens = []
    for row in res_folder.all():
        tok = row[0]
        folder_name = row[1]
        if tok.expires_at and tok.expires_at < now:
            continue
        folder_tokens.append(
            FolderSharePublicForList(
                id=tok.id,
                folder_id=tok.folder_id,
                token=tok.token,
                url=f"{base}/photos/public/{tok.token}",
                folder_name=folder_name,
                created_at=tok.created_at,
                expires_at=tok.expires_at,
            )
        )
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
    tok = await db.scalar(select(PhotoFolderShareToken).where(PhotoFolderShareToken.id == token_id))
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


async def _resolve_token(db: AsyncSession, token: str) -> tuple[Photo, PhotoFolder]:
    res = await db.execute(select(PhotoShareToken).where(PhotoShareToken.token == token))
    link = res.scalar_one_or_none()
    if not link or link.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Link not found")
    if link.expires_at is not None and link.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Link expired")
    res2 = await db.execute(
        select(Photo).where(Photo.id == link.photo_id, Photo.deleted_at.is_(None))
    )
    photo = res2.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder missing")
    return photo, folder


async def _ensure_thumb(photo_id: uuid.UUID, folder: PhotoFolder, photo: Photo, size: int) -> bool:
    p = photos_storage.thumb_path(photo_id, size)
    if p.exists():
        return True
    original_path = photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
    if not original_path.exists():
        return False
    try:
        await photos_storage.generate_thumbnails_safe(photo_id, original_path)
        return True
    except Exception as exc:
        from PIL.Image import DecompressionBombError
        if isinstance(exc, DecompressionBombError):
            raise
        return False


_THUMB_SIZES = set(photos_storage.THUMB_SIZES)


@router.get("/public-folder/{token}/info")
async def public_folder_info(token: str, db: DbDep) -> dict:
    from sqlalchemy import func

    tok_row = await db.scalar(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token)
    )
    if not tok_row:
        raise HTTPException(status_code=404, detail="Not found")
    _resolve_folder_token_sync_check(tok_row)
    folder = await db.scalar(
        select(PhotoFolder).where(
            PhotoFolder.id == tok_row.folder_id, PhotoFolder.deleted_at.is_(None)
        )
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    count = await db.scalar(
        select(func.count(Photo.id)).where(Photo.folder_id == folder.id, Photo.deleted_at.is_(None))
    )
    return {
        "folder_name": folder.name,
        "photos_count": int(count or 0),
        "created_at": tok_row.created_at.isoformat(),
    }


@router.get("/public-folder/{token}/photos", response_model=PhotoListAnon)
async def public_folder_photos(
    token: str,
    db: DbDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> PhotoListAnon:
    from sqlalchemy import func

    tok_row = await db.scalar(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token)
    )
    if not tok_row:
        raise HTTPException(status_code=404, detail="Not found")
    _resolve_folder_token_sync_check(tok_row)
    base = select(Photo).where(
        Photo.folder_id == tok_row.folder_id, Photo.deleted_at.is_(None), Photo.processed.is_(True)
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    res = await db.execute(
        base.order_by(Photo.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    return PhotoListAnon(
        items=[_photo_to_public_anon(p) for p in res.scalars().all()],
        total=int(total or 0),
        page=page,
        per_page=per_page,
    )


@router.get(
    "/public-folder/{token}/thumbnail/{photo_id}/{size}",
    dependencies=[Depends(RateLimiter(times=60, minutes=1))],
)
async def public_folder_thumbnail(
    token: str,
    photo_id: uuid.UUID,
    size: int,
    db: DbDep,
    format: str = Query(default="webp", pattern="^(webp|avif)$"),
) -> Response:
    if size not in _THUMB_SIZES:
        raise HTTPException(status_code=400, detail="Invalid size")
    tok_row = await db.scalar(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token)
    )
    if not tok_row:
        raise HTTPException(status_code=404, detail="Not found")
    _resolve_folder_token_sync_check(tok_row)
    photo = await db.scalar(
        select(Photo).where(
            Photo.id == photo_id, Photo.folder_id == tok_row.folder_id, Photo.deleted_at.is_(None)
        )
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if format == "avif":
        avif_fs = photos_storage.thumb_avif_path(photo.id, size)
        if not avif_fs.exists():
            raise HTTPException(status_code=404, detail="Thumbnail not available")
        return Response(
            status_code=200,
            headers={
                "X-Accel-Redirect": f"/internal/photos-thumbs/{photo.id}/{size}.avif",
                "Content-Type": "image/avif",
                "Cache-Control": "public, max-age=3600",
            },
        )
    thumb = photos_storage.thumb_path(photo.id, size)
    if not thumb.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/internal/photos-thumbs/{photo.id}/{size}.webp",
            "Content-Type": "image/webp",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/public/{token}/info", response_model=PhotoPublicAnon)
async def public_photo_info(token: str, db: DbDep) -> PhotoPublicAnon:
    photo, folder = await _resolve_token(db, token)
    return PhotoPublicAnon(
        id=photo.id,
        folder_path=folder.path,
        original_name=photo.original_name,
        size_bytes=photo.size_bytes,
        mime_type=photo.mime_type,
        width=photo.width,
        height=photo.height,
        taken_at=photo.taken_at,
        description=photo.description,
        processed=photo.processed,
        created_at=photo.created_at,
    )


@router.get("/public/{token}/thumbnail/{size}", dependencies=[Depends(RateLimiter(times=60, minutes=1))])
async def public_thumbnail(
    token: str,
    size: int,
    db: DbDep,
    format: str = Query(default="webp", pattern="^(webp|avif)$"),
) -> Response:
    if size not in _THUMB_SIZES:
        raise HTTPException(status_code=400, detail="Invalid thumbnail size")
    photo, folder = await _resolve_token(db, token)
    if format == "avif":
        avif_fs = photos_storage.thumb_avif_path(photo.id, size)
        if not avif_fs.exists():
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        return Response(
            status_code=200,
            headers={
                "X-Accel-Redirect": f"/internal/photos-thumbs/{photo.id}/{size}.avif",
                "Content-Type": "image/avif",
                "Cache-Control": "public, max-age=3600",
            },
        )
    webp_fs = photos_storage.thumb_path(photo.id, size)
    if not webp_fs.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/internal/photos-thumbs/{photo.id}/{size}.webp",
            "Content-Type": "image/webp",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/public/{token}/file")
async def public_original(
    token: str,
    db: DbDep,
    download: bool = Query(default=False),
) -> Response:
    from .thumbnails import _serve_original_response

    photo, folder = await _resolve_token(db, token)
    return _serve_original_response(photo, folder, download=download)
