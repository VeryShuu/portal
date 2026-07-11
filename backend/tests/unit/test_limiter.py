from __future__ import annotations

import hashlib
import json
from typing import ClassVar

import pytest
from starlette.requests import Request

from app.core.limiter import email_identifier, real_ip_identifier


def _make_request(
    body: bytes = b"",
    content_type: str = "application/json",
    real_ip: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", content_type.encode()),
    ]
    if real_ip:
        headers.append((b"x-real-ip", real_ip.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/local/login",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_email_identifier_json():
    body = json.dumps({"email": "User@Example.com", "password": "secret"}).encode()
    req = _make_request(body=body, content_type="application/json")
    result = await email_identifier(req)
    expected_hash = hashlib.sha256(b"user@example.com").hexdigest()
    assert result == f"login:email:{expected_hash}"


@pytest.mark.asyncio
async def test_email_identifier_form_urlencoded():
    body = b"email=User%40Example.com&password=secret"
    req = _make_request(body=body, content_type="application/x-www-form-urlencoded")
    result = await email_identifier(req)
    expected_hash = hashlib.sha256(b"user@example.com").hexdigest()
    assert result == f"login:email:{expected_hash}"


@pytest.mark.asyncio
async def test_email_identifier_no_email_falls_back_to_ip():
    body = json.dumps({"password": "secret"}).encode()
    req = _make_request(body=body, content_type="application/json", real_ip="10.0.0.1")
    result = await email_identifier(req)
    assert "login:email:" not in result
    assert "10.0.0.1" in result


@pytest.mark.asyncio
async def test_email_identifier_unknown_content_type_falls_back():
    body = b"some-binary-data"
    req = _make_request(body=body, content_type="text/plain", real_ip="10.0.0.2")
    result = await email_identifier(req)
    assert "login:email:" not in result


@pytest.mark.asyncio
async def test_email_identifier_malformed_json_falls_back():
    body = b"not-json"
    req = _make_request(body=body, content_type="application/json", real_ip="10.0.0.3")
    result = await email_identifier(req)
    assert "login:email:" not in result
    assert "10.0.0.3" in result


@pytest.mark.asyncio
async def test_real_ip_identifier_uses_x_real_ip():
    req = _make_request(real_ip="192.168.1.5")
    result = await real_ip_identifier(req)
    assert result.startswith("192.168.1.5:")


@pytest.mark.asyncio
async def test_real_ip_identifier_fallback_to_client_host():
    req = _make_request()
    result = await real_ip_identifier(req)
    assert result.startswith("127.0.0.1:")


# ── Патч совместимости fastapi-limiter 0.1.6 + starlette 1.x ─────────────────
# В starlette 1.x include_router оставляет в app.routes объекты _IncludedRouter
# без атрибутов path/methods. Оригинальный RateLimiter.__call__ падал с
# AttributeError на route.path. Патч пропускает такие маршруты.


@pytest.mark.asyncio
async def test_rate_limiter_skips_routes_without_path():
    """RateLimiter.__call__ не падает на маршрутах без .path (_IncludedRouter).

    Воспроизводит регрессию starlette 1.x: app.routes содержит wrapper-объекты
    без path/methods. Патч должен их пропускать (getattr с default)."""
    from fastapi_limiter.depends import RateLimiter

    # Патч уже применён при импорте app.core.limiter (см. _patch_* в limiter.py).
    # Проверяем, что __call__ не падает на маршрутах без .path.
    class _FakeRoute:
        """Маршрут БЕЗ path/methods (имитация _IncludedRouter из starlette 1.x)."""

    class _FakeRouteWithDeps:
        """Маршрут С path/methods и dependencies (нормальный APIRoute)."""

        path: ClassVar[str] = "/api/v1/auth/local/login"
        methods: ClassVar[set] = {"POST"}

        def __init__(self) -> None:
            self.dependencies: list = []

    class _FakeApp:
        routes: ClassVar[list] = [_FakeRoute(), _FakeRouteWithDeps(), _FakeRoute()]

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/local/login",
        "headers": [(b"x-real-ip", b"127.0.0.1")],
        "client": ("127.0.0.1", 12345),
        "app": _FakeApp(),
    }
    req = Request(scope, lambda: {"type": "http.request", "body": b"", "more_body": False})  # type: ignore[arg-type]

    rl = RateLimiter(times=5, minutes=15)
    # Мокаем _check чтобы не требовать Redis — важен только обход routes.
    rl._check = async_lambda(0)  # type: ignore[method-assign]  # 0 = not rate-limited
    # Без патча — AttributeError: '_FakeRoute' has no attribute 'path'.
    # С патчем — спокойно проходит, возвращает None (не заблокирован).
    result = await rl(req, response=None)  # type: ignore[arg-type]
    assert result is None


def async_lambda(retval):
    """Создать async-функцию, возвращающую retval (мок для _check)."""
    import asyncio

    async def _fn(*args, **kwargs):
        await asyncio.sleep(0)
        return retval

    return _fn
