"""Unit-тесты для app/api/signature.py (stateless, без БД).

Покрытие:
- _require_module_enabled: 404 на всех эндпоинтах при выключенном модуле
- GET /signature/config: cities / office_phones / support_email / email_domain
- POST /signature/generate: html + filename
- POST /signature/download: заголовки (RFC 5987 для кириллицы, Cache-Control), тело
- GET /signature/admin/settings: admin 200 / non-admin 403
- PUT /signature/admin/settings: сохранение + событие аудита signature.settings_updated
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

from app.schemas.signature import SignatureSettings

_AUDIT_PATCH = "app.services.audit.push_audit_event"
_MODULES_PATCH = "app.api.signature.load_modules_shared"
_LOAD_SETTINGS_PATCH = "app.api.signature.load_signature_settings"
_SAVE_SETTINGS_PATCH = "app.api.signature.save_signature_settings"


def _make_user(role: str = "reader", **attrs) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        preferences={},
        full_name=attrs.pop("full_name", "Петров Иван Сергеевич"),
        lang=attrs.pop("lang", "ru"),
        position=attrs.pop("position", "Инженер"),
        email=attrs.pop("email", "ivan@mage.ru"),
        attributes=attrs.pop("attributes", {}),
    )


def _modules(enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(signature=SimpleNamespace(enabled=enabled))


def _valid_body(**overrides) -> dict:
    base = {
        "name": "Иван",
        "surname": "Петров",
        "position": "Инженер",
        "language": "Ru",
        "device": "PC",
        "city_id": 2,
        "office_phone": "+7 (8152) 400 580",
        "extension": "123",
        "mobile_phone": "+7 (900) 000 0000",
        "email": "ivan@mage.ru",
    }
    base.update(overrides)
    return base


def _build_app(user: SimpleNamespace):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_redis
    from app.api.signature import router

    _app = FastAPI()
    _app.include_router(router)

    async def _fake_user():
        return user

    async def _fake_redis():
        return AsyncMock()

    _app.dependency_overrides[get_current_user] = _fake_user
    _app.dependency_overrides[get_redis] = _fake_redis
    return _app


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


async def _post(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, json=json)


async def _put(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.put(url, json=json)


# ── Module gating (404 when disabled) ────────────────────────────────────────


class TestModuleGating:
    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_config_404_when_disabled(self, mock_modules):
        mock_modules.return_value = _modules(enabled=False)
        app = _build_app(_make_user())
        resp = await _get(app, "/signature/config")
        assert resp.status_code == 404

    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_generate_404_when_disabled(self, mock_modules):
        mock_modules.return_value = _modules(enabled=False)
        app = _build_app(_make_user())
        resp = await _post(app, "/signature/generate", _valid_body())
        assert resp.status_code == 404

    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_download_404_when_disabled(self, mock_modules):
        mock_modules.return_value = _modules(enabled=False)
        app = _build_app(_make_user())
        resp = await _post(app, "/signature/download", _valid_body())
        assert resp.status_code == 404

    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_admin_settings_404_when_disabled(self, mock_modules):
        mock_modules.return_value = _modules(enabled=False)
        app = _build_app(_make_user(role="admin"))
        resp = await _get(app, "/signature/admin/settings")
        assert resp.status_code == 404


# ── GET /config ───────────────────────────────────────────────────────────────


class TestConfig:
    @patch(_LOAD_SETTINGS_PATCH)
    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_returns_form_config(self, mock_modules, mock_load):
        mock_modules.return_value = _modules(enabled=True)
        mock_load.return_value = SignatureSettings()
        app = _build_app(_make_user())

        resp = await _get(app, "/signature/config")

        assert resp.status_code == 200
        body = resp.json()
        assert body["support_email"] == "it@mage.ru"
        assert body["email_domain"] == "mage.ru"
        assert len(body["cities"]) == 4
        assert len(body["office_phones"]) == 4
        assert "prefill" in body

    @patch(_LOAD_SETTINGS_PATCH)
    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_config_prefill_from_profile(self, mock_modules, mock_load):
        mock_modules.return_value = _modules(enabled=True)
        mock_load.return_value = SignatureSettings()
        user = _make_user(
            full_name="Гаврин Михаил Владимирович",
            lang="ru",
            attributes={
                "mobile": "+7 911 000 11 22",
                "telephoneNumber": "8(495)6655566,346",
                "city": "Москва",
            },
        )
        app = _build_app(user)

        resp = await _get(app, "/signature/config")

        assert resp.status_code == 200
        prefill = resp.json()["prefill"]
        # ФИО «Фамилия Имя Отчество» → name=Имя, surname=Фамилия (отчество отброшено)
        assert prefill["surname"] == "Гаврин"
        assert prefill["name"] == "Михаил"
        # городской матчится по нормализованным цифрам (8→7) к office_phones
        assert prefill["office_phone"] == "+7 (495) 66 555 66"
        assert prefill["extension"] == "346"
        assert prefill["mobile_phone"] == "+7 911 000 11 22"
        assert prefill["city_id"] == 2  # Москва
        assert prefill["language"] == "Ru"


# ── POST /generate ──────────────────────────────────────────────────────────


class TestGenerate:
    @patch(_LOAD_SETTINGS_PATCH)
    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_returns_html_and_filename(self, mock_modules, mock_load):
        mock_modules.return_value = _modules(enabled=True)
        mock_load.return_value = SignatureSettings()
        app = _build_app(_make_user())

        resp = await _post(app, "/signature/generate", _valid_body())

        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "ИванПетров_Ru.htm"
        assert "Иван Петров" in body["html"]
        assert "mailto:ivan@mage.ru" in body["html"]

    @patch(_LOAD_SETTINGS_PATCH)
    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_invalid_email_rejected(self, mock_modules, mock_load):
        mock_modules.return_value = _modules(enabled=True)
        mock_load.return_value = SignatureSettings()
        app = _build_app(_make_user())

        resp = await _post(app, "/signature/generate", _valid_body(email="x@gmail.com"))

        assert resp.status_code == 422


# ── POST /download ──────────────────────────────────────────────────────────


class TestDownload:
    @patch(_LOAD_SETTINGS_PATCH)
    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_headers_and_body(self, mock_modules, mock_load):
        mock_modules.return_value = _modules(enabled=True)
        mock_load.return_value = SignatureSettings()
        app = _build_app(_make_user())

        resp = await _post(app, "/signature/download", _valid_body())

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        disposition = resp.headers["content-disposition"]
        assert "attachment" in disposition
        assert f"filename*=UTF-8''{quote('ИванПетров_Ru.htm')}" in disposition
        assert resp.headers["cache-control"] == "no-store, max-age=0"
        assert "Иван Петров" in resp.text


# ── Admin settings ────────────────────────────────────────────────────────────


class TestAdminSettings:
    @patch(_LOAD_SETTINGS_PATCH)
    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_get_settings_admin_ok(self, mock_modules, mock_load):
        mock_modules.return_value = _modules(enabled=True)
        mock_load.return_value = SignatureSettings()
        app = _build_app(_make_user(role="admin"))

        resp = await _get(app, "/signature/admin/settings")

        assert resp.status_code == 200
        assert resp.json()["logo_base_url"] == "http://mage.ru/signature/images/"

    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_get_settings_non_admin_forbidden(self, mock_modules):
        mock_modules.return_value = _modules(enabled=True)
        app = _build_app(_make_user(role="editor"))

        resp = await _get(app, "/signature/admin/settings")

        assert resp.status_code == 403

    @patch(_SAVE_SETTINGS_PATCH)
    @patch(_AUDIT_PATCH, new_callable=AsyncMock)
    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_put_settings_saves_and_audits(self, mock_modules, mock_audit, mock_save):
        mock_modules.return_value = _modules(enabled=True)
        app = _build_app(_make_user(role="admin"))

        payload = SignatureSettings().model_dump()
        resp = await _put(app, "/signature/admin/settings", payload)

        assert resp.status_code == 200
        mock_save.assert_called_once()
        mock_audit.assert_awaited_once()
        assert mock_audit.await_args.kwargs["event_type"] == "signature.settings_updated"
        assert mock_audit.await_args.kwargs["resource_type"] == "signature"

    @patch(_MODULES_PATCH, new_callable=AsyncMock)
    async def test_put_settings_non_admin_forbidden(self, mock_modules):
        mock_modules.return_value = _modules(enabled=True)
        app = _build_app(_make_user(role="editor"))

        resp = await _put(app, "/signature/admin/settings", SignatureSettings().model_dump())

        assert resp.status_code == 403
