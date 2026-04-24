import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import AdminDep
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["modules"])

_SETTINGS_DIR = Path("/data/settings")
_MODULES_FILE = _SETTINGS_DIR / "modules.json"
_SECRET_MASK = "***"

_modules_cache: dict[str, Any] = {}
_CACHE_TTL = 60


# ── Internal models (full secrets) ───────────────────────────────────────────

class ImmichModuleSettings(BaseModel):
    enabled: bool = False
    url: str = "http://immich-server:2283"
    public_url: str = "https://photos.portal.company.local"
    api_key: str = ""
    corp_album_id: str = ""
    widget_limit: int = Field(default=8, ge=1, le=50)


class PeerTubeModuleSettings(BaseModel):
    enabled: bool = False
    url: str = "http://peertube:9000"
    public_url: str = "https://video.company.local"
    client_id: str = ""
    client_secret: str = ""
    svc_username: str = "portal-svc"
    svc_password: str = ""
    channel_id: str = ""
    widget_limit: int = Field(default=6, ge=1, le=50)


class NextcloudModuleSettings(BaseModel):
    enabled: bool = False


class AllModuleSettings(BaseModel):
    immich: ImmichModuleSettings = Field(default_factory=ImmichModuleSettings)
    peertube: PeerTubeModuleSettings = Field(default_factory=PeerTubeModuleSettings)
    nextcloud: NextcloudModuleSettings = Field(default_factory=NextcloudModuleSettings)


# ── OUT models (masked secrets) ───────────────────────────────────────────────

class ImmichModuleOut(BaseModel):
    enabled: bool
    url: str
    public_url: str
    api_key_set: bool
    corp_album_id: str
    widget_limit: int


class PeerTubeModuleOut(BaseModel):
    enabled: bool
    url: str
    public_url: str
    client_id: str
    client_secret_set: bool
    svc_username: str
    svc_password_set: bool
    channel_id: str
    widget_limit: int


class NextcloudModuleOut(BaseModel):
    enabled: bool


class AllModuleSettingsOut(BaseModel):
    immich: ImmichModuleOut
    peertube: PeerTubeModuleOut
    nextcloud: NextcloudModuleOut


# ── IN models ─────────────────────────────────────────────────────────────────

class ImmichModuleIn(BaseModel):
    enabled: bool
    url: str = ""
    public_url: str = ""
    api_key: str | None = None
    corp_album_id: str = ""
    widget_limit: int = Field(default=8, ge=1, le=50)


class PeerTubeModuleIn(BaseModel):
    enabled: bool
    url: str = ""
    public_url: str = ""
    client_id: str = ""
    client_secret: str | None = None
    svc_username: str = ""
    svc_password: str | None = None
    channel_id: str = ""
    widget_limit: int = Field(default=6, ge=1, le=50)


class NextcloudModuleIn(BaseModel):
    enabled: bool


# ── Storage ───────────────────────────────────────────────────────────────────

def load_modules() -> AllModuleSettings:
    now = time.monotonic()
    if _modules_cache.get("data") and now - _modules_cache.get("fetched_at", 0) < _CACHE_TTL:
        return _modules_cache["data"]

    if _MODULES_FILE.exists():
        try:
            data = AllModuleSettings.model_validate_json(_MODULES_FILE.read_text("utf-8"))
            _modules_cache["data"] = data
            _modules_cache["fetched_at"] = now
            return data
        except Exception as exc:
            logger.warning("modules.settings_parse_failed", path=str(_MODULES_FILE), error=str(exc))

    from app.core.config import get_settings as _gs
    s = _gs()
    data = AllModuleSettings(
        immich=ImmichModuleSettings(
            enabled=bool(s.immich_api_key and s.immich_corp_album_id),
            url=s.immich_url or "http://immich-server:2283",
            public_url=s.immich_public_url or "https://photos.portal.company.local",
            api_key=s.immich_api_key or "",
            corp_album_id=s.immich_corp_album_id or "",
        ),
        peertube=PeerTubeModuleSettings(
            enabled=bool(
                s.peertube_client_id
                and s.peertube_client_secret
                and s.peertube_svc_username
                and s.peertube_svc_password
            ),
            url=s.peertube_url or "http://peertube:9000",
            public_url=s.peertube_public_url or "https://video.company.local",
            client_id=s.peertube_client_id or "",
            client_secret=s.peertube_client_secret or "",
            svc_username=s.peertube_svc_username or "portal-svc",
            svc_password=s.peertube_svc_password or "",
            channel_id=s.peertube_channel_id or "",
        ),
    )
    _modules_cache["data"] = data
    _modules_cache["fetched_at"] = now
    return data


def _save_modules(m: AllModuleSettings) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = m.model_dump_json(indent=2).encode("utf-8")
    fd, tmp_path = tempfile.mkstemp(prefix=".modules.", suffix=".json.tmp", dir=str(_SETTINGS_DIR))
    try:
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, _MODULES_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    _modules_cache.clear()
    _invalidate_module_caches()


def invalidate_modules_cache() -> None:
    """Сброс TTL-кэша настроек модулей (для тестов и внешних триггеров)."""
    _modules_cache.clear()
    _invalidate_module_caches()


def _invalidate_module_caches() -> None:
    """Чистит кэши, зависящие от настроек модулей (OAuth-токен PeerTube и т.п.)."""
    try:
        from app.api import videos as _videos
        _videos._token_cache.clear()
    except Exception:
        pass


def _immich_out(m: ImmichModuleSettings) -> ImmichModuleOut:
    return ImmichModuleOut(
        enabled=m.enabled,
        url=m.url,
        public_url=m.public_url,
        api_key_set=bool(m.api_key),
        corp_album_id=m.corp_album_id,
        widget_limit=m.widget_limit,
    )


def _peertube_out(m: PeerTubeModuleSettings) -> PeerTubeModuleOut:
    return PeerTubeModuleOut(
        enabled=m.enabled,
        url=m.url,
        public_url=m.public_url,
        client_id=m.client_id,
        client_secret_set=bool(m.client_secret),
        svc_username=m.svc_username,
        svc_password_set=bool(m.svc_password),
        channel_id=m.channel_id,
        widget_limit=m.widget_limit,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/admin/modules", response_model=AllModuleSettingsOut)
async def get_module_settings(_: AdminDep) -> AllModuleSettingsOut:
    m = load_modules()
    return AllModuleSettingsOut(
        immich=_immich_out(m.immich),
        peertube=_peertube_out(m.peertube),
        nextcloud=NextcloudModuleOut(enabled=m.nextcloud.enabled),
    )


@router.put("/admin/modules/immich", response_model=ImmichModuleOut)
async def update_immich_module(data: ImmichModuleIn, _: AdminDep) -> ImmichModuleOut:
    m = load_modules()
    cur = m.immich
    api_key = cur.api_key if data.api_key is None or data.api_key == _SECRET_MASK else data.api_key
    updated = ImmichModuleSettings(
        enabled=data.enabled,
        url=data.url or cur.url,
        public_url=data.public_url or cur.public_url,
        api_key=api_key,
        corp_album_id=data.corp_album_id,
        widget_limit=data.widget_limit,
    )
    m.immich = updated
    _save_modules(m)
    logger.info("modules.immich_updated", enabled=updated.enabled)
    return _immich_out(updated)


@router.put("/admin/modules/peertube", response_model=PeerTubeModuleOut)
async def update_peertube_module(data: PeerTubeModuleIn, _: AdminDep) -> PeerTubeModuleOut:
    m = load_modules()
    cur = m.peertube
    client_secret = cur.client_secret if data.client_secret is None or data.client_secret == _SECRET_MASK else data.client_secret
    svc_password = cur.svc_password if data.svc_password is None or data.svc_password == _SECRET_MASK else data.svc_password
    updated = PeerTubeModuleSettings(
        enabled=data.enabled,
        url=data.url or cur.url,
        public_url=data.public_url or cur.public_url,
        client_id=data.client_id,
        client_secret=client_secret,
        svc_username=data.svc_username or cur.svc_username,
        svc_password=svc_password,
        channel_id=data.channel_id,
        widget_limit=data.widget_limit,
    )
    m.peertube = updated
    _save_modules(m)
    logger.info("modules.peertube_updated", enabled=updated.enabled)
    return _peertube_out(updated)


@router.put("/admin/modules/nextcloud", response_model=NextcloudModuleOut)
async def update_nextcloud_module(data: NextcloudModuleIn, _: AdminDep) -> NextcloudModuleOut:
    m = load_modules()
    m.nextcloud = NextcloudModuleSettings(enabled=data.enabled)
    _save_modules(m)
    logger.info("modules.nextcloud_updated", enabled=data.enabled)
    return NextcloudModuleOut(enabled=data.enabled)


# ── Test connections ──────────────────────────────────────────────────────────

_TEST_TIMEOUT = 10.0


@router.post("/admin/modules/immich/test")
async def test_immich_connection(_: AdminDep) -> dict[str, Any]:
    """Проверяет Immich: server-info и доступность корпоративного альбома."""
    cfg = load_modules().immich
    result: dict[str, Any] = {"configured": bool(cfg.api_key and cfg.url)}
    if not cfg.url or not cfg.api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Immich URL и API key должны быть заданы",
        )

    headers = {"x-api-key": cfg.api_key, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT) as client:
            resp = await client.get(f"{cfg.url}/api/server/about", headers=headers)
            resp.raise_for_status()
            info = resp.json()
            result["server_ok"] = True
            result["version"] = info.get("version") or info.get("versionUrl", "")
    except httpx.HTTPStatusError as exc:
        result["server_ok"] = False
        result["server_error"] = f"HTTP {exc.response.status_code}"
        return result
    except Exception as exc:
        result["server_ok"] = False
        result["server_error"] = str(exc)
        return result

    if not cfg.corp_album_id:
        result["album_ok"] = None
        result["album_note"] = "Album UUID не задан"
        return result

    try:
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT) as client:
            album_resp = await client.get(
                f"{cfg.url}/api/albums/{cfg.corp_album_id}", headers=headers
            )
            album_resp.raise_for_status()
            album = album_resp.json()
            result["album_ok"] = True
            result["album_name"] = album.get("albumName", "")
            result["asset_count"] = album.get("assetCount", len(album.get("assets", [])))
    except httpx.HTTPStatusError as exc:
        result["album_ok"] = False
        result["album_error"] = f"HTTP {exc.response.status_code}"
    except Exception as exc:
        result["album_ok"] = False
        result["album_error"] = str(exc)

    return result


@router.post("/admin/modules/peertube/test")
async def test_peertube_connection(_: AdminDep) -> dict[str, Any]:
    """Проверяет PeerTube: OAuth2 токен по сервисному аккаунту."""
    cfg = load_modules().peertube
    if not cfg.url or not cfg.client_id or not cfg.client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PeerTube URL, Client ID и Client Secret должны быть заданы",
        )
    if not cfg.svc_username or not cfg.svc_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сервисный аккаунт (username/password) должен быть задан",
        )

    result: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT) as client:
            resp = await client.post(
                f"{cfg.url}/api/v1/users/token",
                data={
                    "client_id": cfg.client_id,
                    "client_secret": cfg.client_secret,
                    "grant_type": "password",
                    "response_type": "code",
                    "username": cfg.svc_username,
                    "password": cfg.svc_password,
                },
            )
            resp.raise_for_status()
            token = resp.json().get("access_token")
            result["token_ok"] = bool(token)
    except httpx.HTTPStatusError as exc:
        result["token_ok"] = False
        result["token_error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        return result
    except Exception as exc:
        result["token_ok"] = False
        result["token_error"] = str(exc)
        return result

    # Счётчик видео (опционально)
    try:
        params: dict[str, str | int] = {"count": 1}
        if cfg.channel_id:
            params["videoChannelId"] = cfg.channel_id
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT) as client:
            videos_resp = await client.get(
                f"{cfg.url}/api/v1/videos",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            videos_resp.raise_for_status()
            result["videos_total"] = videos_resp.json().get("total", 0)
    except Exception as exc:
        result["videos_error"] = str(exc)

    # Сброс токен-кэша, чтобы виджет сразу подхватил свежие настройки
    _invalidate_module_caches()
    return result
