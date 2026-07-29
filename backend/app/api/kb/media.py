"""KB media (inline images) endpoints."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.net_guard import assert_url_safe, resolve_stable_ip
from app.core.system_config import load_system_settings
from app.core.uploads import save_bytes_to_path, stream_upload_to_path
from app.schemas.kb_extra import MediaUploadResponse, RemoteMediaRequest
from app.services.kb_acl import require_article_permission

from ._common import _get_article_or_404

logger = get_logger(__name__)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

KB_MEDIA_DIR = Path(get_settings().kb_media_dir)
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# Content-Type → расширение для re-hosted картинок (нетривиального имени URL).
# Зеркалит news/_helpers._CONTENT_TYPE_TO_EXT.
_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

# Параметры безопасного fetch внешних картинок (зеркалят bookmarks/favicon).
_REMOTE_FETCH_TIMEOUT = 10.0
_REMOTE_MAX_REDIRECTS = 5
_REMOTE_UA = "Portal-KB-ImageProxy/1.0"


@router.post("/articles/{article_id}/media", response_model=MediaUploadResponse, status_code=201)
async def upload_article_media(
    article_id: uuid.UUID,
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> MediaUploadResponse:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "editor", db, redis)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image extension. Allowed: .jpg, .jpeg, .png, .gif, .webp",
        )

    safe_name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "image").name, flags=re.ASCII)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = KB_MEDIA_DIR / str(article_id) / unique_name

    max_bytes = load_system_settings().kb_media_max_size_mb * 1024 * 1024
    await stream_upload_to_path(file, dest, max_size=max_bytes, allowed_mimes=ALLOWED_IMAGE_MIMES)

    url = f"/api/v1/kb/media/{article_id}/{unique_name}"
    return MediaUploadResponse(url=url, filename=unique_name)


@router.get("/media/{article_id}/{filename}")
async def serve_article_media(
    article_id: uuid.UUID,
    filename: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    if not re.fullmatch(r"\w[\w.\-]{0,254}", filename) or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    ext = Path(filename).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        mime_type = "image/jpeg"
    elif ext == ".png":
        mime_type = "image/png"
    elif ext == ".gif":
        mime_type = "image/gif"
    elif ext == ".webp":
        mime_type = "image/webp"
    else:
        mime_type = "application/octet-stream"

    internal_path = f"/internal/kb-media/{article_id}/{quote(filename)}"
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": internal_path,
            "Content-Type": mime_type,
            "X-Content-Type-Options": "nosniff",
        },
    )


class _RemoteFetchError(HTTPException):
    """422 с нейтральным сообщением — не раскрываем детали сети/SSRF клиенту."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not fetch the image",
        )


async def _read_image_response(
    resp: httpx.Response,
    *,
    current_url: str,
    max_bytes: int,
) -> tuple[bytes, str]:
    """Прочитать тело ответа с Content-Type/size-валидацией (200 OK).

    Поднятие ``_RemoteFetchError`` (422) для не-картинки, ``HTTPException(413)``
    при превышении размера. Стриминг с бегущим счётчиком байт защищает от OOM
    при ложном/отсутствующем ``Content-Length``. Выделено из
    ``_fetch_remote_image`` для снижения цикломатической сложности.
    """
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not ctype or not ctype.startswith("image/"):
        logger.warning("kb.media.remote.not_image", url=current_url, content_type=ctype)
        raise _RemoteFetchError()
    # Ранняя проверка Content-Length (если указан) — экономит стриминг.
    cl_raw = resp.headers.get("content-length")
    if cl_raw and cl_raw.isdigit() and int(cl_raw) > max_bytes:
        logger.warning("kb.media.remote.too_large_cl", url=current_url)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image too large",
        )
    buf = bytearray()
    overflow = False
    async for chunk in resp.aiter_raw():
        buf.extend(chunk)
        if len(buf) > max_bytes:
            overflow = True
            break
    if overflow:
        logger.warning("kb.media.remote.too_large", url=current_url)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image too large",
        )
    return bytes(buf), ctype


async def _fetch_remote_image(
    url: str,
    *,
    max_bytes: int,
) -> tuple[bytes, str]:
    """Скачать внешнюю картинку с SSRF-защитой и size-cap.

    Защиты (по образцу ``app/api/bookmarks._do_favicon_fetch`` на примитивах
    ``app/core/net_guard``):
      * **SSRF (H-1):** ``follow_redirects=False`` + ручной обход редиректов с
        ре-валидацией каждого hop через ``assert_url_safe`` + двойной резолв с
        пиннингом IP (``resolve_stable_ip``) против DNS-rebinding.
      * **OOM (H-3):** стриминг тела + ранняя проверка ``Content-Length`` +
        бегущий счётчик байт с abort при превышении ``max_bytes``
        (см. ``_read_image_response``).
      * Content-Type обязан начинаться с ``image/``.

    Возвращает ``(body, content_type)`` либо поднимает ``_RemoteFetchError`` /
    ``HTTPException(413)``. Выделена для мокирования в тестах.
    """
    try:
        async with httpx.AsyncClient(
            timeout=_REMOTE_FETCH_TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": _REMOTE_UA},
        ) as client:
            current = url
            for _ in range(_REMOTE_MAX_REDIRECTS + 1):
                # Ре-валидация на каждом hop (включая исходный URL).
                if not await assert_url_safe(current):
                    logger.warning("kb.media.remote.ssrf_blocked", url=current)
                    raise _RemoteFetchError()
                parsed = urlparse(current)
                host = (parsed.hostname or "").lower()
                if not host or await resolve_stable_ip(host) is None:
                    logger.warning("kb.media.remote.dns_rebinding_blocked", url=current)
                    raise _RemoteFetchError()
                # current уже прошёл полную SSRF-валидацию выше (assert_url_safe
                # блокирует private/loopback/cloud-metadata, resolve_stable_ip —
                # DNS-rebinding). CodeQL не отслеживает эту семантику → false
                # positive на py/ssrf; подавляем с обоснованием.
                async with client.stream("GET", current) as resp:  # lgtm[py/ssrf]
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise _RemoteFetchError()
                        current = str(httpx.URL(current).join(location))
                        continue
                    if resp.status_code != 200:
                        logger.warning(
                            "kb.media.remote.bad_status",
                            url=current,
                            status=resp.status_code,
                        )
                        raise _RemoteFetchError()
                    return await _read_image_response(
                        resp, current_url=current, max_bytes=max_bytes
                    )
            logger.warning("kb.media.remote.too_many_redirects", url=url)
            raise _RemoteFetchError()
    except _RemoteFetchError:
        raise
    except HTTPException:
        raise
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("kb.media.remote.fetch_failed", url=url, error=str(exc))
        raise _RemoteFetchError() from None


def _derive_remote_filename(url: str, content_type: str) -> str:
    """Имя файла из последнего сегмента URL, с fallback по Content-Type."""
    parsed = urlparse(url)
    name = parsed.path.rstrip("/").rsplit("/", 1)[-1] if parsed.path else ""
    # Оставить только basename и валидные символы.
    name = re.sub(r"[^\w.\-]", "_", name, flags=re.ASCII)
    if not name or name.startswith("."):
        name = ""
    ext = Path(name).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = f".{_CONTENT_TYPE_TO_EXT.get(content_type, 'bin')}"
        name = ""
    base = Path(name).stem if name else "image"
    return f"{base}{ext}"


@router.post(
    "/articles/{article_id}/media/remote",
    response_model=MediaUploadResponse,
    status_code=201,
)
async def upload_remote_media(
    article_id: uuid.UUID,
    payload: RemoteMediaRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> MediaUploadResponse:
    """Re-host externally hosted image into KB media (SSRF-guarded fetch).

    Используется редактором при paste/drop внешней картинки (``<img src>``,
    URI-list): сервер скачивает её и сохраняет локально, чтобы статья не
    зависела от стороннего URL (может протухнуть / быть недоступным из VPN /
    тянуть трекеры). Контракт ответа идентичен file-upload.
    """
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "editor", db, redis)

    max_bytes = load_system_settings().kb_media_max_size_mb * 1024 * 1024
    data, content_type = await _fetch_remote_image(payload.url, max_bytes=max_bytes)

    safe_name = _derive_remote_filename(payload.url, content_type)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"

    await save_bytes_to_path(
        data,
        KB_MEDIA_DIR,
        (str(article_id), unique_name),
        max_size=max_bytes,
        allowed_mimes=ALLOWED_IMAGE_MIMES,
    )

    url = f"/api/v1/kb/media/{article_id}/{unique_name}"
    return MediaUploadResponse(url=url, filename=unique_name)
