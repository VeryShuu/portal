"""News media routes: cover image, gallery, attachments, inline media."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Body, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.api.deps import CurrentUser, DbDep, EditorDep, RedisDep
from app.core.system_config import load_system_settings
from app.core.uploads import stream_upload_to_path
from app.models.news import News as NewsModel
from app.schemas.kb_extra import MediaUploadResponse
from app.schemas.news import (
    AttachmentPublic,
    GalleryImagePublic,
    NewsPublic,
    ReorderItem,
)
from app.services import news as news_svc

from . import repo
from ._common import (
    ALLOWED_INLINE_IMAGE_MIMES,
    NEWS_MEDIA_DIR,
    emit_news_audit,
    logger,
    require_news_read_access,
)

router = APIRouter()


async def _get_news_or_404(db: DbDep, news_id: uuid.UUID) -> NewsModel:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    return news


# ── Cover ────────────────────────────────────────────────────────────────────


@router.post("/{news_id}/cover", response_model=NewsPublic, summary="Загрузить обложку новости")
async def upload_news_cover(
    news_id: uuid.UUID,
    file: UploadFile,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await _get_news_or_404(db, news_id)
    news = await news_svc.upload_cover(db, news, file)
    logger.info("news.cover_stored", news_id=str(news_id))
    await emit_news_audit(
        redis,
        event_type="news.cover_uploaded",
        actor=editor,
        request=request,
        resource_id=str(news_id),
        resource_title=news.title,
    )
    return cast(NewsPublic, NewsPublic.model_validate(news))


@router.delete("/{news_id}/cover", response_model=NewsPublic, summary="Удалить обложку новости")
async def delete_news_cover(
    news_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await _get_news_or_404(db, news_id)
    news = await news_svc.delete_cover(db, news)
    await emit_news_audit(
        redis,
        event_type="news.cover_deleted",
        actor=editor,
        request=request,
        resource_id=str(news_id),
        resource_title=news.title,
    )
    return cast(NewsPublic, NewsPublic.model_validate(news))


# ── Gallery ──────────────────────────────────────────────────────────────────


@router.get(
    "/{news_id}/gallery", response_model=list[GalleryImagePublic], summary="Галерея новости"
)
async def get_gallery(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> list[GalleryImagePublic]:
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)
    return [
        GalleryImagePublic.model_validate(img)
        for img in await repo.list_gallery_images(db, news_id)
    ]


@router.post(
    "/{news_id}/gallery",
    response_model=GalleryImagePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить фото в галерею",
)
async def upload_gallery_image(
    news_id: uuid.UUID,
    file: UploadFile,
    editor: EditorDep,
    db: DbDep,
) -> GalleryImagePublic:
    news = await _get_news_or_404(db, news_id)
    img = await news_svc.upload_gallery_image(db, news, file)
    return cast(GalleryImagePublic, GalleryImagePublic.model_validate(img))


@router.patch(
    "/{news_id}/gallery/reorder",
    response_model=list[GalleryImagePublic],
    summary="Изменить порядок галереи",
)
async def reorder_gallery(
    news_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    items: list[ReorderItem] = Body(...),
) -> list[GalleryImagePublic]:
    await _get_news_or_404(db, news_id)
    await repo.reorder_gallery_images(
        db, news_id=news_id, items=[(it.id, it.sort_order) for it in items]
    )
    return [
        GalleryImagePublic.model_validate(img)
        for img in await repo.list_gallery_images(db, news_id)
    ]


@router.delete(
    "/{news_id}/gallery/{img_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить фото из галереи",
)
async def delete_gallery_image(
    news_id: uuid.UUID,
    img_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> None:
    img = await news_svc.delete_gallery_image(db, news_id, img_id)
    await emit_news_audit(
        redis,
        event_type="news.gallery_image_deleted",
        actor=editor,
        request=request,
        resource_type="news_gallery_image",
        resource_id=str(img_id),
        resource_title=img.original_name,
        metadata={"news_id": str(news_id)},
    )


# ── Attachments ──────────────────────────────────────────────────────────────


@router.get(
    "/{news_id}/attachments", response_model=list[AttachmentPublic], summary="Вложения новости"
)
async def get_attachments(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> list[AttachmentPublic]:
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)
    return [AttachmentPublic.model_validate(a) for a in await repo.list_attachments(db, news_id)]


@router.post(
    "/{news_id}/attachments",
    response_model=AttachmentPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить вложение",
)
async def upload_attachment(
    news_id: uuid.UUID,
    file: UploadFile,
    editor: EditorDep,
    db: DbDep,
) -> AttachmentPublic:
    news = await _get_news_or_404(db, news_id)
    att = await news_svc.upload_attachment(db, news, file)
    return cast(AttachmentPublic, AttachmentPublic.model_validate(att))


@router.get("/{news_id}/attachments/{att_id}/download", summary="Скачать вложение")
async def download_attachment(
    news_id: uuid.UUID,
    att_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> FileResponse:
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)

    att = await repo.get_attachment(db, news_id=news_id, att_id=att_id)
    if not att:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    file_path = NEWS_MEDIA_DIR / str(news_id) / "attachments" / att.filename
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=att.original_name,
        media_type=att.mime_type or "application/octet-stream",
    )


@router.delete(
    "/{news_id}/attachments/{att_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить вложение",
)
async def delete_attachment(
    news_id: uuid.UUID,
    att_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> None:
    att = await news_svc.delete_attachment(db, news_id, att_id)
    await emit_news_audit(
        redis,
        event_type="news.attachment_deleted",
        actor=editor,
        request=request,
        resource_type="news_attachment",
        resource_id=str(att_id),
        resource_title=att.original_name,
        metadata={"news_id": str(news_id)},
    )


# ── Inline media ─────────────────────────────────────────────────────────────


@router.post(
    "/{news_id}/inline-media",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить инлайн-изображение в тело новости",
)
async def upload_news_inline_media(
    news_id: uuid.UUID,
    file: UploadFile,
    editor: EditorDep,
    db: DbDep,
) -> MediaUploadResponse:
    await _get_news_or_404(db, news_id)

    safe_name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "image").name)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = NEWS_MEDIA_DIR / str(news_id) / "inline" / unique_name

    max_bytes = load_system_settings().kb_media_max_size_mb * 1024 * 1024
    await stream_upload_to_path(
        file, dest, max_size=max_bytes, allowed_mimes=ALLOWED_INLINE_IMAGE_MIMES
    )

    url = f"/api/v1/news/{news_id}/inline-media/{unique_name}"
    return MediaUploadResponse(url=url, filename=unique_name)


@router.get("/{news_id}/inline-media/{filename}", summary="Получить инлайн-изображение новости")
async def serve_news_inline_media(
    news_id: uuid.UUID,
    filename: str,
    user: CurrentUser,
    db: DbDep,
) -> Response:
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,254}", filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    internal_path = f"/internal/news-media/{news_id}/inline/{filename}"
    return Response(
        status_code=200,
        headers={"X-Accel-Redirect": internal_path, "Content-Type": ""},
    )
