from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["videos"])

_THUMB_CACHE_TTL = 3600
_PEERTUBE_TIMEOUT = 10.0

_token_cache: dict[str, str | float] = {}


class VideoItem(BaseModel):
    uuid: str
    name: str
    duration: int
    views: int
    thumbnail_url: str
    watch_url: str
    created_at: str


class VideosRecentResponse(BaseModel):
    configured: bool
    public_url: str = ""
    items: list[VideoItem] = []


class VideosConfigResponse(BaseModel):
    configured: bool
    public_url: str = ""


def _is_embed_ready() -> bool:
    from app.api.modules import load_modules
    m = load_modules()
    return m.peertube.enabled and bool(m.peertube.public_url or m.peertube.url)


def _is_configured() -> bool:
    from app.api.modules import load_modules
    m = load_modules()
    return m.peertube.enabled and bool(
        m.peertube.url
        and m.peertube.client_id
        and m.peertube.client_secret
        and m.peertube.svc_username
        and m.peertube.svc_password
    )


async def _get_oauth_token() -> str:
    now = time.monotonic()
    if _token_cache.get("token") and now < float(_token_cache.get("expires_at", 0)):
        return str(_token_cache["token"])

    from app.api.modules import load_modules
    pt = load_modules().peertube
    async with httpx.AsyncClient(timeout=_PEERTUBE_TIMEOUT) as client:
        resp = await client.post(
            f"{pt.url}/api/v1/users/token",
            data={
                "client_id": pt.client_id,
                "client_secret": pt.client_secret,
                "grant_type": "password",
                "response_type": "code",
                "username": pt.svc_username,
                "password": pt.svc_password,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    token = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + max(expires_in - 60, 60)
    return token


def _peertube_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


@router.get("/videos/config", response_model=VideosConfigResponse)
async def get_videos_config(_: CurrentUser) -> VideosConfigResponse:
    if not _is_embed_ready():
        return VideosConfigResponse(configured=False)
    from app.api.modules import load_modules
    pt = load_modules().peertube
    return VideosConfigResponse(configured=True, public_url=pt.public_url or pt.url)


@router.get("/videos/recent", response_model=VideosRecentResponse)
async def get_recent_videos(_: CurrentUser) -> VideosRecentResponse:
    if not _is_configured():
        return VideosRecentResponse(configured=False)

    from app.api.modules import load_modules
    pt = load_modules().peertube
    limit = pt.widget_limit

    try:
        token = await _get_oauth_token()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.error("peertube.token_failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Video service unavailable") from exc

    params: dict[str, str | int] = {"count": limit, "sort": "-createdAt"}
    if pt.channel_id:
        params["videoChannelId"] = pt.channel_id

    url = f"{pt.url}/api/v1/videos"
    try:
        async with httpx.AsyncClient(timeout=_PEERTUBE_TIMEOUT) as client:
            resp = await client.get(url, headers=_peertube_headers(token), params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("peertube.videos_fetch_failed", status=exc.response.status_code)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Video service unavailable") from exc
    except httpx.RequestError as exc:
        logger.error("peertube.videos_request_error", error=str(exc))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Video service unavailable") from exc

    public_base = pt.public_url or pt.url
    items: list[VideoItem] = []
    for v in data.get("data", []):
        uuid = v.get("uuid", "")
        thumb_path = v.get("thumbnailPath", "")
        items.append(
            VideoItem(
                uuid=uuid,
                name=v.get("name", ""),
                duration=int(v.get("duration", 0)),
                views=int(v.get("views", 0)),
                thumbnail_url=f"/api/v1/videos/thumbnail/{uuid}" if uuid else "",
                watch_url=f"{public_base}/videos/watch/{uuid}" if uuid else "",
                created_at=v.get("createdAt", ""),
            )
        )
        _ = thumb_path

    return VideosRecentResponse(configured=True, public_url=public_base, items=items)


@router.get("/videos/thumbnail/{uuid}", response_class=Response)
async def get_video_thumbnail(uuid: str, _: CurrentUser) -> Response:
    if not _is_configured():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    from app.api.modules import load_modules
    pt = load_modules().peertube
    try:
        token = await _get_oauth_token()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning("peertube.thumbnail_token_failed", uuid=uuid, error=str(exc))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc

    thumb_url = f"{pt.url}/lazy-static/thumbnails/{uuid}.jpg"
    try:
        async with httpx.AsyncClient(timeout=_PEERTUBE_TIMEOUT) as client:
            resp = await client.get(thumb_url, headers=_peertube_headers(token))
            resp.raise_for_status()
            data = resp.content
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning("peertube.thumbnail_fetch_failed", uuid=uuid, error=str(exc))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc

    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": f"public, max-age={_THUMB_CACHE_TTL}"},
    )
