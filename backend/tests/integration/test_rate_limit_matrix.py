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
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from tests.conftest import _CSRF_TOKEN

if TYPE_CHECKING:
    from fastapi_limiter.depends import RateLimiter

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


def _discover_rate_limited_routes(app) -> list[tuple[str, str, int]]:
    """Вернуть ``[(method, full_path, times), ...]`` для всех endpoints с RateLimiter.

    ``full_path`` — путь **со всеми parent-prefix'ами** (``/api/v1/news/...``,
    а не голый ``/{news_id}/...``). Это критично: тест стучится на реальный URL
    и ожидает 429, а не 404 от несуществующего пути.

    Реализация version-agnostic:

    - **FastAPI ≥0.137** (PR fastapi/fastapi#15785): ``include_router`` перестал
      flatten'ить маршруты и кладёт ``_IncludedRouter``-обёртки. Публичный
      ``iter_route_contexts(app.routes)`` корректно разворачивает их и даёт
      ``RouteContext.path`` уже со склейкой всех parent-prefix'ов (внутренне
      через ``include_context.prefix + route.path``). Используем его — это
      единственный надёжный источник полного пути.

    - **FastAPI ≤0.136**: ``iter_route_contexts`` отсутствует, ``app.routes``
      уже плоское (все ``APIRoute`` с готовым полным ``route.path``). Обходим
      напрямую. Duck-typing обёрток ``original_router.routes`` тут не нужен —
      обёрток просто нет.

    Поиск RateLimiter идёт по ``dependant.dependencies`` (как и ранее):
    ``Depends(RateLimiter(...))`` сохраняется как ``Dependant`` с
    ``.call == RateLimiter``-инстансом.
    """
    from fastapi.routing import APIRoute

    # Преференс: публичный API FastAPI ≥0.137, дающий полные пути.
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # FastAPI <0.137 — плоское app.routes
        iter_route_contexts = None  # type: ignore[assignment]

    found: list[tuple[str, str, int]] = []

    if iter_route_contexts is not None:
        for ctx in iter_route_contexts(app.routes):
            route = ctx.route
            if not isinstance(route, APIRoute):
                continue
            rate_limiter = _find_rate_limiter(route.dependant)
            if rate_limiter is None:
                continue
            method = _first_http_method(ctx.methods)
            if method is None:
                continue
            # ``ctx.path`` — property; на типизирован как ``str | None``, но для
            # реального APIRoute путь всегда есть (FastAPI строит его из
            # ``include_context.path_for(route)``). Assert сужает тип для mypy.
            assert ctx.path is not None
            found.append((method, ctx.path, int(rate_limiter.times)))
    else:
        # FastAPI ≤0.136: маршруты уже плоские, route.path несёт полный путь.
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            rate_limiter = _find_rate_limiter(route.dependant)
            if rate_limiter is None:
                continue
            method = _first_http_method(route.methods)
            if method is None:
                continue
            found.append((method, route.path, int(rate_limiter.times)))
    return found


def _find_rate_limiter(dependant) -> RateLimiter | None:
    """Найти ``RateLimiter``-зависимость в ``dependant.dependencies``.

    FastAPI хранит зависимости как ``Dependant``; ``.call`` — callable (для
    ``Depends(RateLimiter(...))`` — экземпляр ``RateLimiter``). Возвращает
    инстанс лимитера или ``None``.
    """
    from fastapi_limiter.depends import RateLimiter

    for dep in dependant.dependencies:
        if isinstance(dep.call, RateLimiter):
            return dep.call
    return None


def _first_http_method(methods: set[str] | None) -> str | None:
    """Первый HTTP-метод маршрута (GET приоритетнее), исключая HEAD/OPTIONS."""
    real = [m for m in (methods or set()) if m not in ("HEAD", "OPTIONS")]
    if not real:
        return None
    return "GET" if "GET" in real else next(iter(real))


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
    Включает проверки parent-prefix эндпоинтов (``/news``, ``/photos``):
    именно они теряли prefix в баге FastAPI 0.137+ (PR fastapi/fastapi#15785),
    из-за чего матрица стучалась на несуществующие пути и ловила 404 вместо 429.
    Эти assertions ловят регрессию на уровне discovery, раньше матрицы.
    """
    routes = _discover_rate_limited_routes(app)
    paths = {p for _, p, _ in routes}
    # Должны найтись как минимум поиск, login, refresh, files/download.
    assert any("/search" in p for p in paths), paths
    assert any("login" in p for p in paths), paths
    assert any("/files/download" in p for p in paths), paths
    # Parent-prefix эндпоинты — регрессионная проверка на потерю prefix'а.
    assert any(p.startswith("/api/v1/news/") for p in paths), paths
    assert any(p.startswith("/api/v1/photos/") for p in paths), paths
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
        # helpdesk: весь пакет гейтится ``require_helpdesk_module`` на
        # объединяющем роутере (``app/api/helpdesk/__init__.py``). При
        # выключенном модуле (дефолт в test env — нет modules.json) gate
        # отдаёт 404 раньше, чем сработает RateLimiter, для ЛЮБОГО
        # helpdesk-эндпоинта (tickets/agents/settings/draft-attachments/...).
        # Лимит проверяется через целевые тесты с включённым модулем в
        # test_rate_limit_endpoints.py — поэтому весь префикс /helpdesk/
        # исключаем из матрицы целиком.
        "/helpdesk/",
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
