from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_video(uuid: str = "vid-uuid-1", name: str = "Test Video", duration: int = 120) -> dict:
    return {
        "uuid": uuid,
        "name": name,
        "duration": duration,
        "views": 42,
        "createdAt": "2025-03-01T10:00:00.000Z",
        "thumbnailPath": f"/lazy-static/thumbnails/{uuid}.jpg",
    }


def _make_settings(
    peertube_url: str = "http://peertube:9000",
    peertube_public_url: str = "https://video.example.com",
    peertube_client_id: str = "client-id",
    peertube_client_secret: str = "client-secret",
    peertube_svc_username: str = "portal-svc",
    peertube_svc_password: str = "svc-password",
    peertube_channel_id: str = "",
) -> MagicMock:
    s = MagicMock()
    s.peertube_url = peertube_url
    s.peertube_public_url = peertube_public_url
    s.peertube_client_id = peertube_client_id
    s.peertube_client_secret = peertube_client_secret
    s.peertube_svc_username = peertube_svc_username
    s.peertube_svc_password = peertube_svc_password
    s.peertube_channel_id = peertube_channel_id
    return s


def _make_sys_settings(peertube_widget_limit: int = 6) -> MagicMock:
    s = MagicMock()
    s.peertube_widget_limit = peertube_widget_limit
    return s


def _make_token_resp(token: str = "access-token-123", expires_in: int = 3600) -> MagicMock:
    r = MagicMock()
    r.json.return_value = {"access_token": token, "expires_in": expires_in}
    r.raise_for_status = MagicMock()
    return r


# ── _is_configured ────────────────────────────────────────────────────────────

def test_is_configured_true():
    with patch("app.api.videos.get_settings", return_value=_make_settings()):
        from app.api.videos import _is_configured
        assert _is_configured() is True


def test_is_configured_false_missing_url():
    with patch("app.api.videos.get_settings", return_value=_make_settings(peertube_url="")):
        from app.api.videos import _is_configured
        assert _is_configured() is False


def test_is_configured_false_missing_client_id():
    with patch("app.api.videos.get_settings", return_value=_make_settings(peertube_client_id="")):
        from app.api.videos import _is_configured
        assert _is_configured() is False


def test_is_configured_false_missing_credentials():
    with patch("app.api.videos.get_settings", return_value=_make_settings(peertube_svc_password="")):
        from app.api.videos import _is_configured
        assert _is_configured() is False


# ── _thumb_cache_path ─────────────────────────────────────────────────────────

def test_thumb_cache_path_deterministic():
    from app.api.videos import _thumb_cache_path
    p1 = _thumb_cache_path("uuid-abc")
    p2 = _thumb_cache_path("uuid-abc")
    assert p1 == p2
    assert p1.suffix == ".jpg"


def test_thumb_cache_path_different_uuids():
    from app.api.videos import _thumb_cache_path
    assert _thumb_cache_path("uuid-1") != _thumb_cache_path("uuid-2")


def test_thumb_cache_path_uses_sha256():
    from app.api.videos import _thumb_cache_path
    uuid = "test-video-uuid"
    expected_name = hashlib.sha256(uuid.encode()).hexdigest() + ".jpg"
    assert _thumb_cache_path(uuid).name == expected_name


# ── get_videos_config ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_videos_config_not_configured():
    with patch("app.api.videos._is_configured", return_value=False):
        from app.api.videos import get_videos_config
        result = await get_videos_config(MagicMock())
        assert result.configured is False
        assert result.public_url == ""


@pytest.mark.asyncio
async def test_videos_config_configured():
    with (
        patch("app.api.videos._is_configured", return_value=True),
        patch("app.api.videos.get_settings", return_value=_make_settings()),
    ):
        from app.api.videos import get_videos_config
        result = await get_videos_config(MagicMock())
        assert result.configured is True
        assert result.public_url == "https://video.example.com"


@pytest.mark.asyncio
async def test_videos_config_fallback_to_internal_url():
    s = _make_settings(peertube_public_url="")
    with (
        patch("app.api.videos._is_configured", return_value=True),
        patch("app.api.videos.get_settings", return_value=s),
    ):
        from app.api.videos import get_videos_config
        result = await get_videos_config(MagicMock())
        assert result.public_url == "http://peertube:9000"


# ── get_recent_videos — not configured ───────────────────────────────────────

@pytest.mark.asyncio
async def test_recent_videos_not_configured():
    with patch("app.api.videos._is_configured", return_value=False):
        from app.api.videos import get_recent_videos
        result = await get_recent_videos(MagicMock())
        assert result.configured is False
        assert result.items == []
        assert result.public_url == ""


# ── get_recent_videos — success path ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_recent_videos_returns_items():
    videos = [_make_video("uuid-1"), _make_video("uuid-2")]
    token_resp = _make_token_resp()
    videos_resp = MagicMock()
    videos_resp.json.return_value = {"data": videos, "total": 2}
    videos_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.get = AsyncMock(return_value=videos_resp)

    with (
        patch("app.api.videos._is_configured", return_value=True),
        patch("app.api.videos.get_settings", return_value=_make_settings()),
        patch("app.api.videos.load_system_settings", return_value=_make_sys_settings(6)),
        patch("app.api.videos._token_cache", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.videos import get_recent_videos
        result = await get_recent_videos(MagicMock())

    assert result.configured is True
    assert len(result.items) == 2
    assert result.items[0].uuid == "uuid-1"


@pytest.mark.asyncio
async def test_recent_videos_limit_applied():
    videos = [_make_video(f"uuid-{i}") for i in range(10)]
    token_resp = _make_token_resp()
    videos_resp = MagicMock()
    videos_resp.json.return_value = {"data": videos, "total": 10}
    videos_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.get = AsyncMock(return_value=videos_resp)

    with (
        patch("app.api.videos._is_configured", return_value=True),
        patch("app.api.videos.get_settings", return_value=_make_settings()),
        patch("app.api.videos.load_system_settings", return_value=_make_sys_settings(3)),
        patch("app.api.videos._token_cache", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.videos import get_recent_videos
        result = await get_recent_videos(MagicMock())

    assert len(result.items) <= 3


@pytest.mark.asyncio
async def test_recent_videos_thumbnail_url_format():
    videos = [_make_video("test-uuid-xyz")]
    token_resp = _make_token_resp()
    videos_resp = MagicMock()
    videos_resp.json.return_value = {"data": videos}
    videos_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.get = AsyncMock(return_value=videos_resp)

    with (
        patch("app.api.videos._is_configured", return_value=True),
        patch("app.api.videos.get_settings", return_value=_make_settings()),
        patch("app.api.videos.load_system_settings", return_value=_make_sys_settings()),
        patch("app.api.videos._token_cache", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.videos import get_recent_videos
        result = await get_recent_videos(MagicMock())

    item = result.items[0]
    assert item.thumbnail_url == "/api/v1/videos/thumbnail/test-uuid-xyz"
    assert "test-uuid-xyz" in item.watch_url


@pytest.mark.asyncio
async def test_recent_videos_watch_url_uses_public_url():
    videos = [_make_video("uuid-watch")]
    token_resp = _make_token_resp()
    videos_resp = MagicMock()
    videos_resp.json.return_value = {"data": videos}
    videos_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.get = AsyncMock(return_value=videos_resp)

    with (
        patch("app.api.videos._is_configured", return_value=True),
        patch("app.api.videos.get_settings", return_value=_make_settings()),
        patch("app.api.videos.load_system_settings", return_value=_make_sys_settings()),
        patch("app.api.videos._token_cache", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.videos import get_recent_videos
        result = await get_recent_videos(MagicMock())

    assert result.items[0].watch_url.startswith("https://video.example.com")


# ── _get_oauth_token — cache ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_token_cached_on_second_call():
    token_resp = _make_token_resp()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=token_resp)

    fake_cache: dict = {}
    fake_cache["token"] = "cached-token"
    fake_cache["expires_at"] = time.monotonic() + 3000

    with (
        patch("app.api.videos.get_settings", return_value=_make_settings()),
        patch("app.api.videos._token_cache", fake_cache),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.videos import _get_oauth_token
        token = await _get_oauth_token()

    assert token == "cached-token"
    mock_client.post.assert_not_called()


# ── thumbnail proxy ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_thumbnail_not_configured():
    import httpx as _httpx
    with patch("app.api.videos._is_configured", return_value=False):
        from app.api.videos import get_video_thumbnail
        with pytest.raises(_httpx.HTTPStatusError if False else Exception):
            pass
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_video_thumbnail("some-uuid", MagicMock())
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_thumbnail_fetches_from_peertube():
    uuid = "fresh-uuid"
    token_resp = _make_token_resp()
    thumb_resp = MagicMock()
    thumb_resp.content = b"THUMB_BYTES"
    thumb_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.get = AsyncMock(return_value=thumb_resp)

    with (
        patch("app.api.videos._is_configured", return_value=True),
        patch("app.api.videos._token_cache", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.videos import get_video_thumbnail
        response = await get_video_thumbnail(uuid, MagicMock())

    assert response.body == b"THUMB_BYTES"
    assert "public" in response.headers.get("Cache-Control", "")
