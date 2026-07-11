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

from fastapi import Request, Response


def _patch_rate_limiter_for_starlette1() -> None:
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
            raise Exception(
                "You must call FastAPILimiter.init in startup event of fastapi!"
            )
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
            FastAPILimiter.lua_sha = await FastAPILimiter.redis.script_load(
                FastAPILimiter.lua_script
            )
            pexpire = await self._check(key)
        if pexpire != 0:
            return await callback(request, response, pexpire)

    RateLimiter.__call__ = _patched_call  # type: ignore[method-assign]


# Патч применяется при импорте модуля (до старта приложения и регистрации роутов).
_patch_rate_limiter_for_starlette1()


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
