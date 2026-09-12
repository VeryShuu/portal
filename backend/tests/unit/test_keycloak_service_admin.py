"""Tests for keycloak.py admin/sync functions.

Покрытие:
- _get_kc_settings_async: Redis-версия / кэш / обновление
- get_jwks: кэш-хит / cache-miss / HTTP-fetch
- search_users: success
- search_groups: success
- get_admin_users: success
- get_user_groups: success / парсинг path/name
- get_groups_members_map: пустой / с группами / пагинация / subgroups / пропуск без id
- _get_sync_token: кэш / fallback-to-oidc / fresh token
- _get_directory_token: sync configured / fallback
- _get_admin_token: success
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _kc_settings_json(
    url: str = "https://kc.example.com",
    realm: str = "myrealm",
    **kwargs,
) -> str:
    data = {
        "keycloak_url": url,
        "keycloak_realm": realm,
        "oidc_client_id": kwargs.get("oidc_client_id", "portal"),
        "oidc_client_secret": kwargs.get("oidc_client_secret", "s3cr3t"),
        "sync_client_id": kwargs.get("sync_client_id", ""),
        "sync_client_secret": kwargs.get("sync_client_secret", ""),
    }
    return json.dumps(data)


def _patch_kc_settings(tmp_path: Path, **kwargs):
    settings_file = tmp_path / "keycloak-settings.json"
    settings_file.write_text(_kc_settings_json(**kwargs), encoding="utf-8")
    return settings_file


def _make_kc_settings(tmp_path: Path, **kwargs):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = _patch_kc_settings(tmp_path, **kwargs)
    with (
        patch.object(kc, "_KC_SETTINGS_FILE", sf),
        patch.object(kc, "_LEGACY_KC_SETTINGS_FILE", tmp_path / "legacy.json"),
    ):
        return kc._get_kc_settings()


class TestGetKcSettingsAsync:
    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_file(self, tmp_path):
        from app.services import keycloak as kc

        kc._settings_cache.clear()
        sf = _patch_kc_settings(tmp_path)

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with (
            patch("app.services.keycloak.get_version", return_value="v1"),
            patch.object(kc, "_KC_SETTINGS_FILE", sf),
            patch.object(kc, "_LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"),
        ):
            result = await kc._get_kc_settings_async(redis=mock_redis)

        assert result.keycloak_url == "https://kc.example.com"
        kc._settings_cache.clear()

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self, tmp_path):
        from app.services import keycloak as kc
        from app.services.keycloak import _KCSettings

        kc._settings_cache.clear()
        fake = _KCSettings("https://cached.kc.com", "realm1", "cid", "cs")
        kc._settings_cache["data"] = fake
        kc._settings_cache["version"] = "v1"
        kc._settings_cache["fetched_at"] = time.monotonic()

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with patch("app.services.keycloak.get_version", return_value="v1"):
            result = await kc._get_kc_settings_async(redis=mock_redis)

        assert result.keycloak_url == "https://cached.kc.com"
        kc._settings_cache.clear()

    @pytest.mark.asyncio
    async def test_version_change_clears_cache(self, tmp_path):
        from app.services import keycloak as kc
        from app.services.keycloak import _KCSettings

        kc._settings_cache.clear()
        fake = _KCSettings("https://old.kc.com", "realm1", "cid", "cs")
        kc._settings_cache["data"] = fake
        kc._settings_cache["version"] = "old_version"
        kc._settings_cache["fetched_at"] = time.monotonic()

        sf = _patch_kc_settings(tmp_path, url="https://new.kc.com")
        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with (
            patch("app.services.keycloak.get_version", return_value="new_version"),
            patch.object(kc, "_KC_SETTINGS_FILE", sf),
            patch.object(kc, "_LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"),
        ):
            result = await kc._get_kc_settings_async(redis=mock_redis)

        assert result.keycloak_url == "https://new.kc.com"
        kc._settings_cache.clear()

    @pytest.mark.asyncio
    async def test_creates_own_redis_when_none(self, tmp_path):
        from app.services import keycloak as kc

        kc._settings_cache.clear()
        sf = _patch_kc_settings(tmp_path)

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with (
            patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
            patch("app.services.keycloak.get_version", return_value="v42"),
            patch.object(kc, "_KC_SETTINGS_FILE", sf),
            patch.object(kc, "_LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"),
        ):
            result = await kc._get_kc_settings_async()

        assert result.keycloak_url == "https://kc.example.com"
        mock_redis.aclose.assert_awaited()
        kc._settings_cache.clear()


class TestGetJwks:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_keys(self):
        from app.services import keycloak as kc

        kc._JWKS_CACHE.clear()
        kc._JWKS_CACHE["keys"] = [{"kty": "RSA", "kid": "cached"}]
        kc._JWKS_CACHE["fetched_at"] = time.monotonic()
        kc._JWKS_CACHE["version"] = "v1"

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with patch("app.services.keycloak.get_version", return_value="v1"):
            result = await kc.get_jwks(redis=mock_redis)

        assert result == [{"kty": "RSA", "kid": "cached"}]
        kc._JWKS_CACHE.clear()

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_keycloak(self, tmp_path):
        from app.services import keycloak as kc

        kc._JWKS_CACHE.clear()
        kc._settings_cache.clear()

        _patch_kc_settings(tmp_path)
        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"keys": [{"kty": "RSA", "kid": "freshkey"}]}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        kcs = _make_kc_settings(tmp_path)

        with (
            patch("app.services.keycloak.get_version", return_value="v2"),
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
        ):
            result = await kc.get_jwks(redis=mock_redis)

        assert result == [{"kty": "RSA", "kid": "freshkey"}]
        assert kc._JWKS_CACHE["keys"] == [{"kty": "RSA", "kid": "freshkey"}]
        kc._JWKS_CACHE.clear()
        kc._settings_cache.clear()

    @pytest.mark.asyncio
    async def test_own_redis_creation(self, tmp_path):
        from app.services import keycloak as kc

        kc._JWKS_CACHE.clear()
        kc._settings_cache.clear()

        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"keys": [{"kid": "k1"}]}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        kcs = _make_kc_settings(tmp_path)

        with (
            patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
            patch("app.services.keycloak.get_version", return_value="v99"),
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
        ):
            result = await kc.get_jwks()

        assert result == [{"kid": "k1"}]
        mock_redis.aclose.assert_awaited()
        kc._JWKS_CACHE.clear()
        kc._settings_cache.clear()


class TestSearchUsers:
    @pytest.mark.asyncio
    async def test_search_users_success(self, tmp_path):
        from app.services import keycloak as kc

        kc._settings_cache.clear()
        _patch_kc_settings(tmp_path)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{"id": "u1", "username": "alice"}]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        kcs = _make_kc_settings(tmp_path)

        with (
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_directory_token", return_value="tok"),
        ):
            result = await kc.search_users("alice")

        assert result == [{"id": "u1", "username": "alice"}]
        kc._settings_cache.clear()


class TestSearchGroups:
    @pytest.mark.asyncio
    async def test_search_groups_success(self, tmp_path):
        from app.services import keycloak as kc

        kcs = _make_kc_settings(tmp_path)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{"id": "g1", "name": "devs"}]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_directory_token", return_value="tok"),
        ):
            result = await kc.search_groups("devs")

        assert result == [{"id": "g1", "name": "devs"}]
        kc._settings_cache.clear()


class TestGetAdminUsers:
    @pytest.mark.asyncio
    async def test_get_admin_users_success(self, tmp_path):
        from app.services import keycloak as kc

        kcs = _make_kc_settings(tmp_path)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{"id": "u1"}, {"id": "u2"}]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_sync_token", return_value="sync_tok"),
        ):
            result = await kc.get_admin_users(page=0, size=100)

        assert len(result) == 2
        kc._settings_cache.clear()


class TestGetUserGroups:
    @pytest.mark.asyncio
    async def test_returns_group_paths(self, tmp_path):
        from app.services import keycloak as kc

        kcs = _make_kc_settings(tmp_path)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [
            {"id": "g1", "path": "/devs"},
            {"id": "g2", "name": "ops"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_sync_token", return_value="tok"),
        ):
            result = await kc.get_user_groups("user-uuid-123")

        assert "/devs" in result
        assert "ops" in result
        kc._settings_cache.clear()


class TestGetGroupsMembersMap:
    @pytest.mark.asyncio
    async def test_empty_groups(self, tmp_path):
        from app.services import keycloak as kc

        kcs = _make_kc_settings(tmp_path)

        empty_resp = MagicMock()
        empty_resp.raise_for_status = MagicMock()
        empty_resp.json.return_value = []

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=empty_resp)

        with (
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_sync_token", return_value="tok"),
        ):
            result = await kc.get_groups_members_map()

        assert result == {}
        kc._settings_cache.clear()

    @pytest.mark.asyncio
    async def test_groups_with_members(self, tmp_path):
        from app.services import keycloak as kc

        kcs = _make_kc_settings(tmp_path)

        groups_resp = MagicMock()
        groups_resp.raise_for_status = MagicMock()
        groups_resp.json.return_value = [
            {"id": "g1", "path": "/devs", "subGroups": []},
        ]

        members_resp = MagicMock()
        members_resp.raise_for_status = MagicMock()
        members_resp.json.return_value = [
            {"id": "u1"},
            {"id": "u2"},
        ]

        empty_resp = MagicMock()
        empty_resp.raise_for_status = MagicMock()
        empty_resp.json.return_value = []

        call_count = 0

        async def _mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "groups" in url and "members" not in url:
                return groups_resp
            elif "members" in url:
                if call_count <= 3:
                    return members_resp
                return empty_resp
            return empty_resp

        mock_client = AsyncMock()
        mock_client.get = _mock_get

        with (
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_sync_token", return_value="tok"),
        ):
            result = await kc.get_groups_members_map()

        assert "u1" in result
        assert "u2" in result
        assert "/devs" in result["u1"]
        kc._settings_cache.clear()

    @pytest.mark.asyncio
    async def test_group_without_id_skipped(self, tmp_path):
        from app.services import keycloak as kc

        kcs = _make_kc_settings(tmp_path)

        groups_resp = MagicMock()
        groups_resp.raise_for_status = MagicMock()
        groups_resp.json.return_value = [
            {"path": "/no-id-group"},
        ]

        empty_resp = MagicMock()
        empty_resp.raise_for_status = MagicMock()
        empty_resp.json.return_value = []

        async def _mock_get(url, **kwargs):
            if "members" not in url and "groups" in url:
                return groups_resp
            return empty_resp

        mock_client = AsyncMock()
        mock_client.get = _mock_get

        with (
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_sync_token", return_value="tok"),
        ):
            result = await kc.get_groups_members_map()

        assert result == {}
        kc._settings_cache.clear()

    @pytest.mark.asyncio
    async def test_subgroups_flattened(self, tmp_path):
        from app.services import keycloak as kc

        kcs = _make_kc_settings(tmp_path)

        groups_resp = MagicMock()
        groups_resp.raise_for_status = MagicMock()
        groups_resp.json.return_value = [
            {
                "id": "g1",
                "path": "/parent",
                "subGroups": [
                    {"id": "g2", "path": "/parent/child", "subGroups": []},
                ],
            },
        ]

        members_resp = MagicMock()
        members_resp.raise_for_status = MagicMock()
        members_resp.json.return_value = [{"id": "u1"}]

        empty_resp = MagicMock()
        empty_resp.raise_for_status = MagicMock()
        empty_resp.json.return_value = []

        call_count = 0

        async def _mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "members" in url:
                if call_count <= 4:
                    return members_resp
                return empty_resp
            return groups_resp

        mock_client = AsyncMock()
        mock_client.get = _mock_get

        with (
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_sync_token", return_value="tok"),
        ):
            result = await kc.get_groups_members_map()

        assert "u1" in result
        kc._settings_cache.clear()

    @pytest.mark.asyncio
    async def test_pagination_multiple_pages(self, tmp_path):
        from app.services import keycloak as kc

        kcs = _make_kc_settings(tmp_path)

        page_size = 2

        page1_resp = MagicMock()
        page1_resp.raise_for_status = MagicMock()
        page1_resp.json.return_value = [
            {"id": "g1", "path": "/g1", "subGroups": []},
            {"id": "g2", "path": "/g2", "subGroups": []},
        ]

        page2_resp = MagicMock()
        page2_resp.raise_for_status = MagicMock()
        page2_resp.json.return_value = [{"id": "g3", "path": "/g3", "subGroups": []}]

        empty_resp = MagicMock()
        empty_resp.raise_for_status = MagicMock()
        empty_resp.json.return_value = []

        group_call = 0

        async def _mock_get(url, **kwargs):
            nonlocal group_call
            if "members" in url:
                return empty_resp
            group_call += 1
            if group_call == 1:
                return page1_resp
            return page2_resp

        mock_client = AsyncMock()
        mock_client.get = _mock_get

        with (
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_sync_token", return_value="tok"),
        ):
            result = await kc.get_groups_members_map(page_size=page_size)

        assert result == {}
        kc._settings_cache.clear()


class TestGetSyncToken:
    @pytest.mark.asyncio
    async def test_returns_cached_token(self, tmp_path):
        from app.services import keycloak as kc

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="cached_token")
        mock_redis.aclose = AsyncMock()

        with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
            result = await kc._get_sync_token()

        assert result == "cached_token"

    @pytest.mark.asyncio
    async def test_fallback_to_oidc_when_no_sync_client(self, tmp_path):
        from app.services import keycloak as kc
        from app.services.keycloak import _KCSettings

        kcs = _KCSettings("https://kc.example.com", "realm", "portal", "secret")

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.aclose = AsyncMock()

        with (
            patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_admin_token", return_value="oidc_token"),
        ):
            result = await kc._get_sync_token()

        assert result == "oidc_token"

    @pytest.mark.asyncio
    async def test_fetches_fresh_token_with_sync_client(self, tmp_path):
        from app.services import keycloak as kc
        from app.services.keycloak import _KCSettings

        kcs = _KCSettings(
            "https://kc.example.com",
            "realm",
            "portal",
            "secret",
            sync_client_id="sync-client",
            sync_client_secret="sync-secret",
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.aclose = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"access_token": "fresh_tok", "expires_in": 300}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
        ):
            result = await kc._get_sync_token()

        assert result == "fresh_tok"
        mock_redis.set.assert_awaited_once()


class TestGetDirectoryToken:
    @pytest.mark.asyncio
    async def test_uses_sync_client_when_configured(self, tmp_path):
        from app.services import keycloak as kc
        from app.services.keycloak import _KCSettings

        kcs = _KCSettings(
            "https://kc.example.com",
            "realm",
            "portal",
            "secret",
            sync_client_id="sync",
            sync_client_secret="sync-sec",
        )

        with (
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_sync_token", return_value="sync_tok"),
        ):
            result = await kc._get_directory_token()

        assert result == "sync_tok"

    @pytest.mark.asyncio
    async def test_falls_back_to_admin_token(self, tmp_path):
        from app.services import keycloak as kc
        from app.services.keycloak import _KCSettings

        kcs = _KCSettings("https://kc.example.com", "realm", "portal", "secret")

        with (
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_admin_token", return_value="admin_tok"),
        ):
            result = await kc._get_directory_token()

        assert result == "admin_tok"


class TestGetAdminToken:
    @pytest.mark.asyncio
    async def test_returns_access_token(self, tmp_path):
        from app.services import keycloak as kc
        from app.services.keycloak import _KCSettings

        kcs = _KCSettings("https://kc.example.com", "realm", "portal", "secret")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"access_token": "admin_access_tok"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch.object(kc, "_get_kc_settings_async", return_value=kcs),
            patch.object(kc, "_get_kc_http_client", return_value=mock_client),
        ):
            result = await kc._get_admin_token()

        assert result == "admin_access_tok"
