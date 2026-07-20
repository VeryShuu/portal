from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
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
#
# Сами сценарии патча живут ниже (test_patched_call_*): они вызывают
# `patched_call` напрямую, потому что conftest session-fixture подменяет
# `RateLimiter.__call__` no-op'ом для всех unit-тестов (fakeredis не умеет
# Lua SCRIPT). Без прямого вызова тесты проверяли бы stub, а не реальный патч.


def async_lambda(retval):
    """Создать async-функцию, возвращающую retval (мок для _check)."""
    import asyncio

    async def _fn(*args, **kwargs):
        await asyncio.sleep(0)
        return retval

    return _fn


# ── Доп. сценарии patched_call (добиваем ветки патча ADR-043) ──────────────
# Цель: покрыть строки, не затронутые test_rate_limiter_skips_routes_without_path:
#   * FastAPILimiter.redis is None → Exception (контракт «init не вызван»);
#   * route_methods is None → путь всё равно матчится (path-only match);
#   * self.identifier / self.callback — собственные колбэки зависимости;
#   * redis NoScriptException → повторный _check после script_load;
#   * pexpire != 0 → вызывается callback (заблокирован).
#
# ВАЖНО: tests/conftest.py::_stub_fastapi_limiter подменяет RateLimiter.__call__
# no-op'ом для всех unit-тестов (fakeredis не поддерживает Lua SCRIPT). Поэтому
# `await rl(req, response)` тестировал бы stub, а не реальный патч. Чтобы тесты
# патча ADR-043 были честными, вызываем `patched_call` напрямую (экспортирован из
# app.core.limiter на уровне модуля).
from unittest.mock import AsyncMock, MagicMock

from app.core.limiter import patched_call


def _make_request_scope(path: str = "/api/v1/auth/local/login", method: str = "POST"):
    """Скоуп starlette-запроса для тестов __call__ (app добавляется отдельно)."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"x-real-ip", b"127.0.0.1")],
        "client": ("127.0.0.1", 12345),
    }


def _build_req(app_routes: list, path: str = "/api/v1/x", method: str = "POST"):
    """Собирает starlette Request с заданным app.routes."""
    scope = _make_request_scope(path=path, method=method)
    scope["app"] = SimpleNamespace(routes=app_routes)

    # Starlette Request принимает async receive (возвращает Awaitable сообщения).
    # Используем именованную async-функцию вместо lambda: mypy на tests/ строго
    # проверяет сигнатуру, лямбда-синхрон даёт [arg-type]/[return-value].
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def _init_fastapi_limiter_defaults(monkeypatch, *, redis=None) -> None:
    """Устанавливает минимальные дефолты FastAPILimiter, чтобы patched_call мог
    дойти до _check. Без FastAPILimiter.init() (который требует Redis) класс
    имеет identifier=None/callback=None — и патч падает на `await identifier(req)`.

    Имитируем результат init() на минимальном уровне:
    * redis — что-то не-None (реальный Lua не вызывается, _check мокается);
    * identifier — асинхронная функция-заглушка (возвращает rate-key);
    * http_callback — None, если тест переопределяет callback через self.callback.
    """
    from fastapi_limiter import FastAPILimiter

    if redis is not None:
        monkeypatch.setattr(FastAPILimiter, "redis", redis)
    else:
        monkeypatch.setattr(FastAPILimiter, "redis", object())

    async def _default_identifier(request):
        return "test-key"

    monkeypatch.setattr(FastAPILimiter, "identifier", _default_identifier)
    monkeypatch.setattr(FastAPILimiter, "prefix", "fastapi-limiter")


class _FakeRoute:
    """Маршрут без path/methods (имитация _IncludedRouter из starlette 1.x)."""


class _FakeRouteWithDeps:
    """Маршрут с path/methods и dependencies (нормальный APIRoute)."""

    def __init__(self, path: str = "/api/v1/auth/local/login", methods: set | None = None):
        self.path = path
        self.methods = methods if methods is not None else {"POST"}
        self.dependencies: list = []


@pytest.mark.asyncio
async def test_patched_call_raises_when_redis_not_initialized(monkeypatch):
    """Контракт: FastAPILimiter.redis is None → явная ошибка (init не был вызван).

    Защита от тишины: если разработчик забыл FastAPILimiter.init на startup,
    лимитер должен громко падать, а не «пропускать всё»."""
    from fastapi_limiter import FastAPILimiter
    from fastapi_limiter.depends import RateLimiter

    monkeypatch.setattr(FastAPILimiter, "redis", None)

    req = _build_req([_FakeRouteWithDeps()])
    rl = RateLimiter(times=5, minutes=15)

    with pytest.raises(Exception, match=r"must call FastAPILimiter\.init"):
        await patched_call(rl, req, response=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_patched_call_matches_route_with_methods_none(monkeypatch):
    """Ветка: route.methods is None при совпадении path — считается матчем.
    Реально встречается у маршрутов без явного methods (e.g. mounted apps)."""
    from fastapi_limiter.depends import RateLimiter

    _init_fastapi_limiter_defaults(monkeypatch)

    route_no_methods = _FakeRouteWithDeps(path="/api/v1/search", methods=None)
    req = _build_req([route_no_methods], path="/api/v1/search", method="GET")
    rl = RateLimiter(times=5, minutes=15)
    rl._check = async_lambda(0)  # type: ignore[method-assign]

    # Не должно упасть — methods=None, но path совпал → route_index найден.
    result = await patched_call(rl, req, response=None)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_patched_call_uses_custom_identifier_and_callback(monkeypatch):
    """Ветка: self.identifier / self.callback (если заданы у зависимости)
    используются вместо дефолтных FastAPILimiter.*. Это явный API fastapi-limiter:
    каждая RateLimiter-зависимость может переопределить поведение."""
    from fastapi_limiter.depends import RateLimiter

    _init_fastapi_limiter_defaults(monkeypatch)

    identifier_called = []
    callback_called = []

    async def custom_identifier(request):
        identifier_called.append(True)
        return "custom-key"

    async def custom_callback(request, response, pexpire):
        callback_called.append(pexpire)
        return "blocked"

    req = _build_req([_FakeRouteWithDeps(path="/api/v1/test")], path="/api/v1/test")
    rl = RateLimiter(times=5, minutes=15)
    rl._check = async_lambda(500)  # type: ignore[method-assign]  # pexpire != 0 → блокировка
    rl.identifier = custom_identifier
    rl.callback = custom_callback

    result = await patched_call(rl, req, response=None)  # type: ignore[arg-type]
    assert identifier_called == [True]
    assert callback_called == [500]
    assert result == "blocked"


@pytest.mark.asyncio
async def test_patched_call_reloads_lua_script_on_noscripterror(monkeypatch):
    """Ветка: NoScriptException → redis.script_load + повторный _check.

    Redis может забыть загруженный Lua-скрипт (FLUSH/перезапуск), тогда EVALSHA
    падает с NoScriptException. Патч перезагружает скрипт и повторяет проверку."""
    import redis as pyredis
    from fastapi_limiter.depends import RateLimiter

    fake_redis = MagicMock()
    fake_redis.script_load = AsyncMock(return_value="new-sha")
    _init_fastapi_limiter_defaults(monkeypatch, redis=fake_redis)

    req = _build_req([_FakeRouteWithDeps(path="/api/v1/x")], path="/api/v1/x")
    rl = RateLimiter(times=5, minutes=15)

    call_count = {"n": 0}

    async def _check_side_effect(key):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise pyredis.exceptions.NoScriptError("NOSCRIPT No matching script.")
        return 0

    rl._check = _check_side_effect  # type: ignore[method-assign]

    result = await patched_call(rl, req, response=None)  # type: ignore[arg-type]
    assert call_count["n"] == 2  # первый упал, второй прошёл
    fake_redis.script_load.assert_awaited_once()
    assert result is None


@pytest.mark.asyncio
async def test_patched_call_invokes_default_callback_when_blocked(monkeypatch):
    """Ветка: pexpire != 0 → вызывается FastAPILimiter.http_callback (дефолтный,
    т.к. self.callback не задан)."""
    from fastapi_limiter import FastAPILimiter
    from fastapi_limiter.depends import RateLimiter

    _init_fastapi_limiter_defaults(monkeypatch)

    callback_called = []

    async def default_callback(request, response, pexpire):
        callback_called.append(pexpire)
        return "default-blocked"

    monkeypatch.setattr(FastAPILimiter, "http_callback", default_callback)

    req = _build_req([_FakeRouteWithDeps(path="/api/v1/y")], path="/api/v1/y")
    rl = RateLimiter(times=5, minutes=15)
    rl._check = async_lambda(1000)  # type: ignore[method-assign]  # pexpire != 0

    result = await patched_call(rl, req, response=None)  # type: ignore[arg-type]
    assert callback_called == [1000]
    assert result == "default-blocked"


@pytest.mark.asyncio
async def test_patched_call_skips_routes_without_path(monkeypatch):
    """Тот же контракт, что исходный test_rate_limiter_skips_routes_without_path,
    но через прямой вызов patched_call — обходит session-fixture stub из conftest
    и реально тестирует патч ADR-043 (getattr-fallback для _IncludedRouter)."""
    from fastapi_limiter.depends import RateLimiter

    _init_fastapi_limiter_defaults(monkeypatch)

    class _FakeRouteWithDeps2:
        path: str = "/api/v1/auth/local/login"
        methods: ClassVar[set] = {"POST"}

        def __init__(self) -> None:
            self.dependencies: list = []

    class _FakeApp:
        routes: ClassVar[list] = [_FakeRoute(), _FakeRouteWithDeps2(), _FakeRoute()]

    scope = _make_request_scope(path="/api/v1/auth/local/login")
    scope["app"] = _FakeApp()

    async def receive():  # type: ignore[no-untyped-def]
        return {"type": "http.request", "body": b"", "more_body": False}

    req = Request(scope, receive)

    rl = RateLimiter(times=5, minutes=15)
    rl._check = async_lambda(0)  # type: ignore[method-assign]

    # Без патча — AttributeError: '_FakeRoute' has no attribute 'path'.
    # С патчем — спокойно проходит, возвращает None (не заблокирован).
    result = await patched_call(rl, req, response=None)  # type: ignore[arg-type]
    assert result is None
