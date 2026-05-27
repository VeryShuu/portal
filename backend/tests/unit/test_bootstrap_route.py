"""Unit tests for app/api/bootstrap.py."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("httpx", reason="httpx not installed")


def _make_user() -> SimpleNamespace:
    from datetime import UTC, datetime

    return SimpleNamespace(
        id=uuid.uuid4(),
        role="reader",
        email="u@test.local",
        full_name="Test User",
        avatar_url=None,
        keycloak_id=None,
        keycloak_groups=None,
        is_active=True,
        department=None,
        position=None,
        phone=None,
        presence_status="online",
        lang="ru",
        created_at=datetime.now(UTC),
        auth_source="keycloak",
        attributes={},
        last_login_at=None,
        staff_sort_order=None,
        staff_hidden=False,
        notify_email=True,
        notify_inapp=True,
        preferences={},
    )


def _make_branding_out():
    from app.api.branding import BrandingSettings, BrandingSettingsOut

    return BrandingSettingsOut(
        **BrandingSettings().model_dump(),
        has_favicon=False,
        has_login_bg=False,
        has_logo=False,
        allowed_iframe_origins=[],
    )


def _make_modules_out():
    from app.api.bootstrap import _DEFAULT_MODULES

    return _DEFAULT_MODULES


def _make_gallery_out():
    from app.core.system_config import GalleryLinksOut

    return GalleryLinksOut(
        photo_gallery_url=None,
        photo_gallery_mode="external",
        photo_gallery_new_tab=False,
        video_gallery_url=None,
    )


def _build_app(user, db, redis=None):
    from fastapi import FastAPI

    from app.api.bootstrap import router
    from app.api.deps import get_current_user, get_db, get_redis

    app = FastAPI()
    app.include_router(router)

    if redis is None:
        redis = AsyncMock()

    async def _user():
        return user

    async def _db():
        return db

    async def _redis():
        return redis

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    return app


class TestBootstrapRoute:
    @pytest.mark.asyncio
    async def test_bootstrap_success(self):
        import httpx

        user = _make_user()
        db = AsyncMock()
        redis = AsyncMock()
        app = _build_app(user, db, redis)

        branding = _make_branding_out()
        modules = _make_modules_out()
        gallery = _make_gallery_out()

        with patch("app.api.bootstrap.load_modules_shared", AsyncMock(return_value=MagicMock(
            nextcloud=MagicMock(enabled=False),
            photos=MagicMock(),
        ))), \
             patch("app.api.bootstrap.load_system_settings_shared", AsyncMock(return_value=MagicMock(
                 photo_gallery_url=None,
                 photo_gallery_mode="external",
                 photo_gallery_new_tab=False,
                 video_gallery_url=None,
             ))), \
             patch("app.api.bootstrap.get_unread_count", AsyncMock(return_value=3)), \
             patch("app.api.bootstrap._build_branding", return_value=branding):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get("/bootstrap")

        assert r.status_code == 200
        data = r.json()
        assert "user" in data
        assert "branding" in data
        assert "modules" in data
        assert "gallery_links" in data
        assert data["unread_count"] == 3

    @pytest.mark.asyncio
    async def test_bootstrap_modules_failure_uses_defaults(self):
        import httpx

        user = _make_user()
        db = AsyncMock()
        redis = AsyncMock()
        app = _build_app(user, db, redis)

        branding = _make_branding_out()
        gallery = _make_gallery_out()

        with patch("app.api.bootstrap.load_modules_shared", AsyncMock(side_effect=Exception("nc down"))), \
             patch("app.api.bootstrap.load_system_settings_shared", AsyncMock(return_value=MagicMock(
                 photo_gallery_url=None,
                 photo_gallery_mode="external",
                 photo_gallery_new_tab=False,
                 video_gallery_url=None,
             ))), \
             patch("app.api.bootstrap.get_unread_count", AsyncMock(return_value=0)), \
             patch("app.api.bootstrap._build_branding", return_value=branding):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get("/bootstrap")

        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_bootstrap_gallery_failure_uses_defaults(self):
        import httpx

        user = _make_user()
        db = AsyncMock()
        redis = AsyncMock()
        app = _build_app(user, db, redis)

        branding = _make_branding_out()

        with patch("app.api.bootstrap.load_modules_shared", AsyncMock(return_value=MagicMock(
            nextcloud=MagicMock(enabled=False),
            photos=MagicMock(),
        ))), \
             patch("app.api.bootstrap.load_system_settings_shared", AsyncMock(side_effect=Exception("redis down"))), \
             patch("app.api.bootstrap.get_unread_count", AsyncMock(return_value=0)), \
             patch("app.api.bootstrap._build_branding", return_value=branding):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get("/bootstrap")

        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_bootstrap_unread_failure_defaults_to_zero(self):
        import httpx

        user = _make_user()
        db = AsyncMock()
        redis = AsyncMock()
        app = _build_app(user, db, redis)

        branding = _make_branding_out()

        with patch("app.api.bootstrap.load_modules_shared", AsyncMock(return_value=MagicMock(
            nextcloud=MagicMock(enabled=False),
            photos=MagicMock(),
        ))), \
             patch("app.api.bootstrap.load_system_settings_shared", AsyncMock(return_value=MagicMock(
                 photo_gallery_url=None,
                 photo_gallery_mode="external",
                 photo_gallery_new_tab=False,
                 video_gallery_url=None,
             ))), \
             patch("app.api.bootstrap.get_unread_count", AsyncMock(side_effect=Exception("db error"))), \
             patch("app.api.bootstrap._build_branding", return_value=branding):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get("/bootstrap")

        assert r.status_code == 200
        assert r.json()["unread_count"] == 0

    @pytest.mark.asyncio
    async def test_bootstrap_branding_failure_uses_defaults(self):
        import httpx

        user = _make_user()
        db = AsyncMock()
        redis = AsyncMock()
        app = _build_app(user, db, redis)

        with patch("app.api.bootstrap.load_modules_shared", AsyncMock(return_value=MagicMock(
            nextcloud=MagicMock(enabled=False),
            photos=MagicMock(),
        ))), \
             patch("app.api.bootstrap.load_system_settings_shared", AsyncMock(return_value=MagicMock(
                 photo_gallery_url=None,
                 photo_gallery_mode="external",
                 photo_gallery_new_tab=False,
                 video_gallery_url=None,
             ))), \
             patch("app.api.bootstrap.get_unread_count", AsyncMock(return_value=0)), \
             patch("asyncio.to_thread", AsyncMock(side_effect=Exception("disk error"))):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get("/bootstrap")

        assert r.status_code == 200
