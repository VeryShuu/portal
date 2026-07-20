"""Integration: автоматическая matrix-проверка rate-limit для всех endpoints.

Идея: пройти по `app.routes`, найти все маршруты с зависимостью `RateLimiter`,
и для каждого подтвердить, что (times + 1)-й запрос с одного IP отдаёт 429.

Этот тест защищает от регрессий, когда новый endpoint декорируется
`Depends(RateLimiter(...))`, но реально лимит не срабатывает
(например, из-за неверного порядка зависимостей или мока в conftest).
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

import pytest
import pytest_asyncio

from tests.conftest import _CSRF_TOKEN

pytestmark = pytest.mark.asyncio


def _csrf_kwargs(ip: str) -> dict[str, Any]:
    return {
        "headers": {
            "Origin": "http://test",
            "X-Real-IP": ip,
            "x-xsrf-token": _CSRF_TOKEN,
        },
        "cookies": {"XSRF-TOKEN": _CSRF_TOKEN},
    }


def _fill_path_params(path: str) -> str:
    """Подставить безопасные плейсхолдеры в {param}.

    Конкретные значения не важны: rate-limiter срабатывает раньше,
    чем endpoint валидирует id/ресурс/auth.
    """
    out = path
    while "{" in out and "}" in out:
        start = out.index("{")
        end = out.index("}", start)
        name = out[start + 1 : end].split(":", 1)[0]
        if "size" in name:
            value = "200"
        elif "token" in name:
            value = "tok-placeholder"
        else:
            value = "00000000-0000-0000-0000-000000000000"
        out = out[:start] + value + out[end + 1 :]
    return out


def _iter_api_routes(routes):
    """Обойти ``app.routes`` рекурсивно, раскрывая обёртки.

    FastAPI 0.137+ (PR fastapi/fastapi#15785, требует starlette 1.x) меняет
    поведение ``include_router``: вместо flatten'инга дочерних маршрутов в
    ``app.routes`` теперь лежат ``_IncludedRouter`` обёртки **без** атрибута
    ``path`` и без ``routes``, но с ``original_router.routes``. На 0.136 и
    ниже — старое плоское представление (все APIRoute напрямую). Этот
    генератор работает на обеих версиях: при встрече с обёрткой спускается
    в ``original_router.routes`` (если есть).
    """
    for route in routes:
        # ``_IncludedRouter`` — нет ``path``, нет ``routes``, но есть
        # ``original_router``. Имя класса intentional не импортируем — это
        # internal FastAPI, между версиями может переименовываться;
        # duck-typing по отсутствию ``path`` + наличию ``original_router``
        # стабильнее.
        if not hasattr(route, "path") and hasattr(route, "original_router"):
            yield from _iter_api_routes(route.original_router.routes)
        elif not hasattr(route, "path") and hasattr(route, "routes"):
            yield from _iter_api_routes(route.routes)
        else:
            yield route


def _discover_rate_limited_routes(app) -> list[tuple[str, str, int]]:
    """Вернуть [(method, path, times), ...] для всех endpoints с RateLimiter."""
    from fastapi.routing import APIRoute
    from fastapi_limiter.depends import RateLimiter

    found: list[tuple[str, str, int]] = []
    for route in _iter_api_routes(app.routes):
        if not isinstance(route, APIRoute):
            continue
        dependant = route.dependant
        rate_limiter: RateLimiter | None = None
        # FastAPI хранит зависимости как Dependant'ы; .call — это callable
        # (для Depends(RateLimiter(...)) — экземпляр RateLimiter).
        for dep in dependant.dependencies:
            if isinstance(dep.call, RateLimiter):
                rate_limiter = dep.call
                break
        if rate_limiter is None:
            continue
        # Берём первый метод, исключая HEAD/OPTIONS.
        methods = [m for m in (route.methods or set()) if m not in ("HEAD", "OPTIONS")]
        if not methods:
            continue
        method = "GET" if "GET" in methods else next(iter(methods))
        found.append((method, route.path, int(rate_limiter.times)))
    return found


@pytest_asyncio.fixture
async def limiter(redis_client):
    """Поднять реальный fastapi-limiter поверх redis для теста."""
    from fastapi_limiter import FastAPILimiter
    from fastapi_limiter.depends import RateLimiter

    import tests.conftest as _root_conftest
    from app.core.limiter import real_ip_identifier

    saved_call = RateLimiter.__call__
    if _root_conftest._real_rate_limiter_call is not None:
        RateLimiter.__call__ = _root_conftest._real_rate_limiter_call  # type: ignore[method-assign]

    await FastAPILimiter.init(redis_client, identifier=real_ip_identifier)
    try:
        # Очистим возможные ключи лимитера, чтобы тест был детерминирован.
        try:
            keys = await redis_client.keys("fastapi-limiter:*")
            if keys:
                await redis_client.delete(*keys)
        except Exception:
            pass
        yield redis_client
    finally:
        RateLimiter.__call__ = saved_call  # type: ignore[method-assign]
        with contextlib.suppress(Exception):
            await FastAPILimiter.close()


async def test_discovery_finds_known_endpoints(app):
    """Sanity-check: discovery должен находить хотя бы несколько известных endpoints.

    Если падает — значит сломан inspect, и matrix-тест ниже бесполезен.
    """
    routes = _discover_rate_limited_routes(app)
    paths = {p for _, p, _ in routes}
    # Должны найтись как минимум поиск, login, refresh, files/download.
    assert any("/search" in p for p in paths), paths
    assert any("login" in p for p in paths), paths
    assert any("/files/download" in p for p in paths), paths
    assert len(routes) >= 10, f"too few rate-limited routes discovered: {len(routes)}"


async def test_all_rate_limited_endpoints_return_429(limiter, app):
    """Для каждого rate-limited endpoint: (times+1)-й запрос с одного IP → 429.

    Тест проверяет именно факт срабатывания лимита, а не корректность бизнес-логики
    — endpoints могут вернуть 401/403/404/422 на ранних запросах, это нормально.
    """
    from httpx import ASGITransport, AsyncClient

    routes = _discover_rate_limited_routes(app)

    # Маршруты, у которых dependency-цепочка (Nextcloud, файловое хранилище,
    # внешние OCS-эндпоинты, module-gate) короткозамыкается до 503/404 ДО
    # запуска RateLimiter. Лимит проверяется через целевые тесты в
    # test_rate_limit_endpoints.py.
    skip_path_fragments = (
        "/ocs/v2.php",
        "/files/folders/",
        "/files/download",
        "/files/preview",
        # helpdesk: require_helpdesk_module отдаёт 404 при выключенном модуле
        # раньше, чем срабатывает RateLimiter (как все module-gated роутеры).
        "/helpdesk/tickets",
    )

    transport = ASGITransport(app=app)
    failures: list[str] = []

    for idx, (method, raw_path, times) in enumerate(routes):
        if any(frag in raw_path for frag in skip_path_fragments):
            continue
        # Уникальный IP на каждый endpoint, чтобы лимиты не пересекались.
        ip = f"10.99.{idx // 256}.{idx % 256}"
        path = _fill_path_params(raw_path)
        if not path.startswith("/api/v1"):
            path = "/api/v1" + path

        async with AsyncClient(
            transport=transport, base_url="http://test", **_csrf_kwargs(ip)
        ) as ac:
            fn = getattr(ac, method.lower())
            kwargs: dict[str, Any] = {}
            # Для login email-identifier требует JSON с email — иначе fallback на IP,
            # что нам и нужно, но пустое тело может упасть до лимитера.
            if "login" in raw_path:
                kwargs["json"] = {
                    "email": f"matrix-{uuid.uuid4().hex[:6]}@portal.local",
                    "password": "wrong",
                }
            elif method in ("POST", "PUT", "PATCH"):
                kwargs["json"] = {}

            last_status: int | None = None
            for _ in range(times + 1):
                try:
                    r = await fn(path, **kwargs)
                    last_status = r.status_code
                except Exception as exc:  # pragma: no cover - диагностика
                    failures.append(
                        f"{method} {path} (times={times}): unexpected exception {exc!r}"
                    )
                    break

            if last_status != 429:
                failures.append(
                    f"{method} {path} (times={times}): last status {last_status}, expected 429"
                )

    assert not failures, "Rate-limit not triggered for endpoints:\n  " + "\n  ".join(failures)
