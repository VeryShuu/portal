"""Кастомный identifier для fastapi-limiter.

Использует X-Real-IP (выставляется nginx из $remote_addr, клиент подделать не может)
вместо X-Forwarded-For (который fastapi-limiter по умолчанию берёт из первого
элемента, позволяя байпас через подделанный заголовок).

NB: намеренно БЕЗ ``from __future__ import annotations`` — иначе аннотации
``_patched_call`` становятся строками, и после monkey-patch FastAPI перестаёт
узнавать ``Request``/``Response`` как special-case (``lenient_issubclass``
строки → False) → 422 ``loc=["query","request"]`` на rate-limited endpoints.
"""

import hashlib
import ipaddress
from collections.abc import Callable
from typing import cast

from fastapi import Request, Response


def _patch_rate_limiter_for_starlette1() -> Callable[..., object]:
    """Совместимость fastapi-limiter 0.1.6 со starlette 1.x.

    В starlette 1.x ``include_router`` оставляет в ``app.routes`` объекты
    ``_IncludedRouter`` (wrapper'ы включённых роутеров) без атрибутов ``path``
    и ``methods``. ``RateLimiter.__call__`` итерирует ``request.app.routes`` и
    обращается к ``route.path`` → ``AttributeError`` на каждом rate-limited
    endpoint (включая ``/auth/local/login``).

    Патчит ``__call__`` так, чтобы маршруты без ``path``/``methods``
    пропускались. Upstream не починен: fastapi-limiter 0.2.0 переписан на
    ``pyrate_limiter`` (другой API) и содержит ту же ошибку. См. AGENTS.md:
    «не использовать slowapi» — fastapi-limiter зафиксирован в стеке.
    """
    import redis as pyredis
    from fastapi_limiter import FastAPILimiter
    from fastapi_limiter.depends import RateLimiter

    async def _patched_call(self: RateLimiter, request: Request, response: Response) -> None:
        if not FastAPILimiter.redis:
            raise Exception("You must call FastAPILimiter.init in startup event of fastapi!")
        route_index = 0
        dep_index = 0
        for i, route in enumerate(request.app.routes):
            # starlette 1.x: _IncludedRouter не имеет path/methods — пропускаем.
            route_path = getattr(route, "path", None)
            if route_path is None:
                continue
            route_methods = getattr(route, "methods", None)
            if route_path == request.scope["path"] and (
                route_methods is None or request.method in route_methods
            ):
                route_index = i
                for j, dependency in enumerate(route.dependencies):
                    if self is dependency.dependency:
                        dep_index = j
                        break

        identifier = self.identifier or FastAPILimiter.identifier
        callback = self.callback or FastAPILimiter.http_callback
        rate_key = await identifier(request)
        key = f"{FastAPILimiter.prefix}:{rate_key}:{route_index}:{dep_index}"
        try:
            pexpire = await self._check(key)
        except pyredis.exceptions.NoScriptError:
            # redis-py выбрасывает NoScriptError (не «NoScriptException» —
            # опечатка в оригинальном fastapi-limiter ловит несуществующий
            # класс → при реальном NoScript except-branch падал бы с
            # AttributeError во время обработки исключения). Здесь ловим
            # правильное исключение: EVALSHA провалился (скрипт забыт после
            # FLUSH/перезапуска Redis) → перезагружаем и повторяем.
            FastAPILimiter.lua_sha = await FastAPILimiter.redis.script_load(
                FastAPILimiter.lua_script
            )
            pexpire = await self._check(key)
        if pexpire != 0:
            return cast(None, await callback(request, response, pexpire))

    RateLimiter.__call__ = _patched_call
    return _patched_call


# Патч применяется при импорте модуля (до старта приложения и регистрации роутов).
# Сохраняем ссылку для тестов — чтобы они могли вызывать именно патченный __call__,
# а не session-fixture stub из tests/conftest.py::_stub_fastapi_limiter.
patched_call = _patch_rate_limiter_for_starlette1()


async def real_ip_identifier(request: Request) -> str:
    """Идентификатор для rate-limit: X-Real-IP + путь.

    Порядок источников:
    1. X-Real-IP — выставляется trusted proxy (nginx) из $remote_addr.
    2. request.client.host — fallback при обращении без proxy (dev/tests).
    """
    real_ip = request.headers.get("X-Real-IP")
    if not real_ip:
        real_ip = request.client.host if request.client else "unknown"
    return f"{real_ip}:{request.scope['path']}"


# ── Probe-bypass: доверенные docker-internal подсети ──────────────────────
# Synthetic-проба (cron run_synthetic_probe, каждые 5 мин) логинится через
# настоящий /auth/local/login под сервисным аккаунтом. IP-лимит (5/15min)
# срабатывает на 6-м запросе → 429. Probe приходит из docker-internal сети
# (screenshot-service → nginx → backend). Запросы из этой подсети —
# service-to-service, и X-Real-IP их ставит trusted nginx (внешний клиент
# подделать не может), поэтому байпас безопасен. См. probe_bypass_rate_limit.
TRUSTED_INTERNAL_CIDR = ipaddress.ip_network("172.16.0.0/12")


def is_trusted_internal_ip(ip_str: str) -> bool:
    """IP из docker-internal bridge-подсети (172.16.0.0/12)?

    Покрывает весь default Docker bridge range (172.16–172.31). Используется
    для probe-bypass rate-limiter'а. 10.x/192.168.x намеренно НЕ включены —
    это могут быть пользовательские клиенты из корпоративной LAN.
    """
    try:
        return ipaddress.ip_address(ip_str) in TRUSTED_INTERNAL_CIDR
    except ValueError:
        return False


def _real_ip(request: Request) -> str:
    """Только IP-часть (без пути) — единый источник для bypass-проверки.

    Тот же приоритет, что у real_ip_identifier: X-Real-IP (nginx) → client.host.
    """
    real_ip = request.headers.get("X-Real-IP")
    if not real_ip:
        real_ip = request.client.host if request.client else "unknown"
    return cast(str, real_ip)


def probe_bypass_rate_limit(times: int, minutes: int) -> Callable[..., object]:
    """Dependency-фабрика: RateLimiter с bypass для доверенных internal-IP.

    Заменяет прямой ``Depends(RateLimiter(times=N, minutes=M))`` на эндпоинтах,
    куда стучится synthetic-проба (login). Для запросов из docker-internal
    подсети (172.16.0.0/12 — probe/exporters) лимит скипается; для остальных
    действует стандартный RateLimiter. Brute-force-защита для реальных
    пользователей сохраняется: внешний атакующий не имеет IP из 172.16/12 и не
    может подделать X-Real-IP (его ставит nginx из $remote_addr).

    NB: email-лимит (RateLimiter с identifier=email_identifier) отдельно не
    обёртывается — probe укладывается в него (3 логина/15мин < 10).
    """
    from fastapi_limiter.depends import RateLimiter

    limiter = RateLimiter(times=times, minutes=minutes)

    async def _dependency(request: Request) -> None:
        if is_trusted_internal_ip(_real_ip(request)):
            return  # probe / service-to-service — пропускаем без счётчика
        await limiter(request, None)

    return _dependency


async def email_identifier(request: Request) -> str:
    """Идентификатор для local login по email (SHA-256), с fallback на real IP.

    Парсит как JSON, так и application/x-www-form-urlencoded, чтобы исключить
    обход лимита по email через смену Content-Type.
    """
    try:
        content_type = request.headers.get("content-type", "")
        email = ""
        if "application/json" in content_type:
            import json as _json

            raw = await request.body()
            body = _json.loads(raw) if raw else {}
            email = (body.get("email") or "").strip().lower() if isinstance(body, dict) else ""
        elif (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            form = await request.form()
            email = (str(form.get("email") or "")).strip().lower()
        if not email:
            return await real_ip_identifier(request)
        email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        return f"login:email:{email_hash}"
    except Exception:
        return await real_ip_identifier(request)
