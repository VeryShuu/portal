"""CSRF two-origin (ADR-050, инкремент 6): публичный контур обучения — второй
доверенный Origin наравне с порталом.

Контракты:
- Origin learn-домена принимается, когда задан ``learning_base_url``;
- настройка пуста (контур не введён) → learn-Origin отклоняется, допуск
  не расширяется;
- произвольный сторонний Origin отклоняется в обоих случаях;
- learning-login (origin-only путь) с learn-Origin не падает на CSRF
  (уходит дальше по аутентификации).
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.system_config import _schemas as schemas

PORTAL = "http://portal.test"
LEARN = "https://learn.mage.ru"


def _install_settings(monkeypatch, **over: Any) -> None:
    data = schemas.SystemSettings(portal_base_url=PORTAL, **over)
    import app.core.system_config as sc

    monkeypatch.setattr(sc, "load_system_settings", lambda: data)


@pytest.fixture()
def make_app(app, monkeypatch):
    """Conftest-``app`` (fakeredis в state) + патч настроек под контур."""

    def _make(**over: Any):
        _install_settings(monkeypatch, **over)
        return app

    return _make


async def _post_news(ac: AsyncClient, origin: str) -> tuple[int, str]:
    token = ac.cookies.get("XSRF-TOKEN") or ""
    resp = await ac.post(
        "/api/v1/news",
        json={"title": "x", "body": "y"},
        headers={"Origin": origin, "X-XSRF-TOKEN": token},
    )
    detail = ""
    if resp.status_code == 403:
        detail = resp.json().get("detail", "")
    return resp.status_code, detail


async def test_learn_origin_accepted_when_configured(make_app):
    application = make_app(learning_base_url=LEARN)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url=PORTAL) as ac:
        await ac.get("/health")  # выдаёт XSRF-TOKEN
        code, detail = await _post_news(ac, LEARN)
        assert (code, "CSRF" in detail) != (403, True), (
            f"learn-Origin должен приниматься при заданном learning_base_url; got {code} {detail}"
        )


async def test_learn_origin_rejected_when_not_configured(make_app):
    application = make_app()  # learning_base_url="" (дефолт)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url=PORTAL) as ac:
        await ac.get("/health")
        code, detail = await _post_news(ac, LEARN)
        assert code == 403
        assert "CSRF" in detail


async def test_evil_origin_rejected_even_with_learn_configured(make_app):
    application = make_app(learning_base_url=LEARN)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url=PORTAL) as ac:
        await ac.get("/health")
        code, detail = await _post_news(ac, "https://evil.example.com")
        assert code == 403
        assert "CSRF" in detail


async def test_portal_origin_still_accepted(make_app):
    application = make_app(learning_base_url=LEARN)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url=PORTAL) as ac:
        await ac.get("/health")
        code, detail = await _post_news(ac, PORTAL)
        assert (code, "CSRF" in detail) != (403, True)


async def test_learning_login_origin_only_from_learn_domain(make_app):
    """Оба шага passwordless-входа (запрос кода, verify) — origin-only пути:
    с learn-Origin запросы проходят CSRF (ответ по существу, а не 403 CSRF)."""
    application = make_app(learning_base_url=LEARN)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url=LEARN) as ac:
        resp = await ac.post(
            "/api/v1/auth/learning/login",
            json={"email": "nobody@example.com"},
            headers={"Origin": LEARN},
        )
        assert resp.status_code != 403, f"got {resp.status_code} {resp.text}"
        verify = await ac.post(
            "/api/v1/auth/learning/verify",
            json={"email": "nobody@example.com", "code": "123456"},
            headers={"Origin": LEARN},
        )
        assert verify.status_code != 403, f"got {verify.status_code} {verify.text}"
