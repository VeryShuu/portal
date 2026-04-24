"""Unit-тесты для модуля фотогалереи (Immich integration)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_asset(asset_id: str = "abc123", created_at: str = "2025-01-15T10:00:00.000Z") -> dict:
    return {
        "id": asset_id,
        "originalFileName": f"photo_{asset_id}.jpg",
        "fileCreatedAt": created_at,
    }


def _make_settings(
    immich_url: str = "http://immich:2283",
    immich_public_url: str = "https://photos.example.com",
    immich_api_key: str = "test-key",
    immich_corp_album_id: str = "album-uuid-123",
) -> MagicMock:
    s = MagicMock()
    s.immich_url = immich_url
    s.immich_public_url = immich_public_url
    s.immich_api_key = immich_api_key
    s.immich_corp_album_id = immich_corp_album_id
    return s


def _make_sys_settings(immich_widget_limit: int = 8) -> MagicMock:
    s = MagicMock()
    s.immich_widget_limit = immich_widget_limit
    return s


# ── _is_configured ────────────────────────────────────────────────────────────

def test_is_configured_true():
    with patch("app.api.photos.get_settings", return_value=_make_settings()):
        from app.api.photos import _is_configured
        assert _is_configured() is True


def test_is_configured_false_missing_api_key():
    with patch("app.api.photos.get_settings", return_value=_make_settings(immich_api_key="")):
        from app.api.photos import _is_configured
        assert _is_configured() is False


def test_is_configured_false_missing_album():
    with patch("app.api.photos.get_settings", return_value=_make_settings(immich_corp_album_id="")):
        from app.api.photos import _is_configured
        assert _is_configured() is False


def test_is_configured_false_missing_url():
    with patch("app.api.photos.get_settings", return_value=_make_settings(immich_url="")):
        from app.api.photos import _is_configured
        assert _is_configured() is False


# ── _thumb_cache_path ─────────────────────────────────────────────────────────

def test_thumb_cache_path_deterministic():
    from app.api.photos import _thumb_cache_path
    p1 = _thumb_cache_path("asset-abc")
    p2 = _thumb_cache_path("asset-abc")
    assert p1 == p2
    assert p1.suffix == ".jpg"


def test_thumb_cache_path_different_assets():
    from app.api.photos import _thumb_cache_path
    p1 = _thumb_cache_path("asset-1")
    p2 = _thumb_cache_path("asset-2")
    assert p1 != p2


def test_thumb_cache_path_uses_sha256():
    from app.api.photos import _thumb_cache_path
    asset_id = "test-asset-id"
    expected_name = hashlib.sha256(asset_id.encode()).hexdigest() + ".jpg"
    assert _thumb_cache_path(asset_id).name == expected_name


# ── get_recent_photos — not configured ───────────────────────────────────────

@pytest.mark.asyncio
async def test_recent_photos_not_configured():
    with patch("app.api.photos._is_configured", return_value=False):
        from app.api.photos import get_recent_photos
        result = await get_recent_photos(MagicMock())
        assert result.configured is False
        assert result.items == []
        assert result.public_url == ""


# ── get_recent_photos — sorting ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recent_photos_sorted_by_date_desc():
    assets = [
        _make_asset("id1", "2025-01-10T00:00:00.000Z"),
        _make_asset("id3", "2025-01-30T00:00:00.000Z"),
        _make_asset("id2", "2025-01-20T00:00:00.000Z"),
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = assets
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with (
        patch("app.api.photos._is_configured", return_value=True),
        patch("app.api.photos.get_settings", return_value=_make_settings()),
        patch("app.api.photos.load_system_settings", return_value=_make_sys_settings(8)),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.photos import get_recent_photos
        result = await get_recent_photos(MagicMock())

    assert result.configured is True
    assert [item.id for item in result.items] == ["id3", "id2", "id1"]


@pytest.mark.asyncio
async def test_recent_photos_limit_applied():
    assets = [_make_asset(f"id{i}", f"2025-01-{i:02d}T00:00:00.000Z") for i in range(1, 16)]
    mock_resp = MagicMock()
    mock_resp.json.return_value = assets
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with (
        patch("app.api.photos._is_configured", return_value=True),
        patch("app.api.photos.get_settings", return_value=_make_settings()),
        patch("app.api.photos.load_system_settings", return_value=_make_sys_settings(5)),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.photos import get_recent_photos
        result = await get_recent_photos(MagicMock())

    assert len(result.items) == 5


@pytest.mark.asyncio
async def test_recent_photos_thumbnail_url_format():
    assets = [_make_asset("uuid-abc")]
    mock_resp = MagicMock()
    mock_resp.json.return_value = assets
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with (
        patch("app.api.photos._is_configured", return_value=True),
        patch("app.api.photos.get_settings", return_value=_make_settings()),
        patch("app.api.photos.load_system_settings", return_value=_make_sys_settings()),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.photos import get_recent_photos
        result = await get_recent_photos(MagicMock())

    item = result.items[0]
    assert item.thumbnail_url == "/api/v1/photos/thumbnail/uuid-abc"
    assert "photos.example.com" in item.original_url
    assert "uuid-abc" in item.original_url


# ── get_photo_thumbnail ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_thumbnail_not_configured_returns_404():
    with patch("app.api.photos._is_configured", return_value=False):
        from app.api.photos import get_photo_thumbnail
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_photo_thumbnail("any-id", MagicMock())
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_thumbnail_cache_hit(tmp_path: Path):
    asset_id = "cached-asset"
    cache_file = tmp_path / f"{hashlib.sha256(asset_id.encode()).hexdigest()}.jpg"
    cache_file.write_bytes(b"fake-jpeg-data")

    with (
        patch("app.api.photos._is_configured", return_value=True),
        patch("app.api.photos._THUMB_CACHE_DIR", tmp_path),
        patch("app.api.photos._thumb_cache_path", return_value=cache_file),
    ):
        from app.api.photos import get_photo_thumbnail
        response = await get_photo_thumbnail(asset_id, MagicMock())

    assert response.body == b"fake-jpeg-data"
    assert response.media_type == "image/jpeg"
    assert "public" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_thumbnail_cache_miss_fetches_from_immich(tmp_path: Path):
    asset_id = "new-asset"
    fake_jpeg = b"\xff\xd8\xff\xe0fake-jpeg"

    mock_resp = MagicMock()
    mock_resp.content = fake_jpeg
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with (
        patch("app.api.photos._is_configured", return_value=True),
        patch("app.api.photos.get_settings", return_value=_make_settings()),
        patch("app.api.photos._THUMB_CACHE_DIR", tmp_path),
        patch("app.api.photos._thumb_cache_path", return_value=tmp_path / "nonexistent.jpg"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.photos import get_photo_thumbnail
        response = await get_photo_thumbnail(asset_id, MagicMock())

    assert response.body == fake_jpeg
    assert response.media_type == "image/jpeg"
    assert "max-age=3600" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_thumbnail_immich_error_returns_404():
    import httpx as _httpx

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    http_err = _httpx.HTTPStatusError("not found", request=MagicMock(), response=mock_resp)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=http_err)

    with (
        patch("app.api.photos._is_configured", return_value=True),
        patch("app.api.photos.get_settings", return_value=_make_settings()),
        patch("app.api.photos._thumb_cache_path", return_value=Path("/nonexistent/path.jpg")),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.photos import get_photo_thumbnail
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_photo_thumbnail("bad-id", MagicMock())
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_recent_photos_immich_502_on_request_error():
    import httpx as _httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=_httpx.ConnectError("connection refused"))

    with (
        patch("app.api.photos._is_configured", return_value=True),
        patch("app.api.photos.get_settings", return_value=_make_settings()),
        patch("app.api.photos.load_system_settings", return_value=_make_sys_settings()),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        from app.api.photos import get_recent_photos
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_recent_photos(MagicMock())
        assert exc_info.value.status_code == 502
