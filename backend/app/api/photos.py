from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["photos"])

_THUMB_CACHE_DIR = Path("/data/cache/immich")
_THUMB_REDIS_TTL = 3600
_IMMICH_TIMEOUT = 10.0


class PhotoItem(BaseModel):
    id: str
    file_name: str
    local_date_time: str
    thumbnail_url: str
    original_url: str


class PhotosRecentResponse(BaseModel):
    configured: bool
    public_url: str = ""
    items: list[PhotoItem] = []


def _is_configured() -> bool:
    from app.api.modules import load_modules
    m = load_modules()
    return m.immich.enabled and bool(m.immich.url and m.immich.api_key and m.immich.corp_album_id)


def _immich_headers() -> dict[str, str]:
    from app.api.modules import load_modules
    return {"x-api-key": load_modules().immich.api_key, "Accept": "application/json"}


def _thumb_cache_path(asset_id: str) -> Path:
    safe = hashlib.sha256(asset_id.encode()).hexdigest()
    return _THUMB_CACHE_DIR / f"{safe}.jpg"


@router.get("/photos/recent", response_model=PhotosRecentResponse)
async def get_recent_photos(_: CurrentUser) -> PhotosRecentResponse:
    if not _is_configured():
        return PhotosRecentResponse(configured=False)

    from app.api.modules import load_modules
    cfg = load_modules().immich
    limit = cfg.widget_limit

    url = f"{cfg.url}/api/albums/{cfg.corp_album_id}/assets"
    try:
        async with httpx.AsyncClient(timeout=_IMMICH_TIMEOUT) as client:
            resp = await client.get(url, headers=_immich_headers(), params={"page": 1, "pageSize": limit})
            resp.raise_for_status()
            raw: list[dict] = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("immich.album_fetch_failed", status=exc.response.status_code, album_id=cfg.corp_album_id)
        return PhotosRecentResponse(configured=True, public_url=cfg.public_url or cfg.url, items=[])
    except httpx.RequestError as exc:
        logger.error("immich.album_request_error", error=str(exc))
        return PhotosRecentResponse(configured=True, public_url=cfg.public_url or cfg.url, items=[])

    raw_sorted = sorted(raw, key=lambda a: a.get("fileCreatedAt", ""), reverse=True)[:limit]

    public_url = cfg.public_url or cfg.url
    items = [
        PhotoItem(
            id=asset["id"],
            file_name=asset.get("originalFileName", asset["id"]),
            local_date_time=asset.get("fileCreatedAt", ""),
            thumbnail_url=f"/api/v1/photos/thumbnail/{asset['id']}",
            original_url=f"{public_url}/photos/{asset['id']}",
        )
        for asset in raw_sorted
    ]

    return PhotosRecentResponse(configured=True, public_url=public_url, items=items)


@router.get("/photos/thumbnail/{asset_id}", response_class=Response)
async def get_photo_thumbnail(asset_id: str, _: CurrentUser) -> Response:
    if not _is_configured():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    cache_path = _thumb_cache_path(asset_id)
    if cache_path.exists():
        data = cache_path.read_bytes()
        return Response(
            content=data,
            media_type="image/jpeg",
            headers={"Cache-Control": f"public, max-age={_THUMB_REDIS_TTL}"},
        )

    from app.api.modules import load_modules
    cfg = load_modules().immich
    url = f"{cfg.url}/api/assets/{asset_id}/thumbnail"
    try:
        async with httpx.AsyncClient(timeout=_IMMICH_TIMEOUT) as client:
            resp = await client.get(url, headers=_immich_headers(), params={"size": "preview"})
            resp.raise_for_status()
            data = resp.content
    except httpx.HTTPStatusError as exc:
        logger.warning("immich.thumbnail_fetch_failed", asset_id=asset_id, status=exc.response.status_code)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except httpx.RequestError as exc:
        logger.error("immich.thumbnail_request_error", asset_id=asset_id, error=str(exc))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY) from exc

    try:
        _THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
    except OSError as exc:
        logger.warning("immich.thumbnail_cache_write_failed", asset_id=asset_id, error=str(exc))

    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": f"public, max-age={_THUMB_REDIS_TTL}"},
    )
