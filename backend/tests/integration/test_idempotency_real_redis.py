"""Real-Redis integration for IdempotencyMiddleware (аудит тестирования 2026-08-23, P2).

Юнит-контур (test_idempotency_middleware.py) работает на fakeredis. Здесь —
production-поведение на настоящем Redis: lease-TTL, in-flight 409, атомарный
WATCH-release и главное — release «старым владельцем» не снимает чужой лок
после takeover (fakeredis исполняет WATCH иначе, чем реальный сервер, и
именно здесь расходения ловятся только интеграцией).

Требует INTEGRATION_REDIS=true (поднятый Redis из settings.redis_url).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid

import httpx
import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.middleware.idempotency import IdempotencyMiddleware, _release_lock_atomic

pytestmark = pytest.mark.asyncio

# TTL-контракт lease-лока: литерал, НЕ импорт из тестируемого модуля
# (review-3: сравнение константы с собой было таутологией — мутация
# _LOCK_TTL 120→1 оставалась зелёной). 120с = осознанный выбор lease
# (докстринг _LOCK_TTL: покрывает максимальную длительность POST).
EXPECTED_LOCK_TTL = 120


def _skip_if_no_redis():
    if os.environ.get("INTEGRATION_REDIS", "false").lower() not in ("1", "true", "yes"):
        pytest.skip("INTEGRATION_REDIS=true required")


async def _make_redis():
    from redis.asyncio import Redis

    from app.core.config import get_settings

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()
    return redis


def _build_app(redis) -> Starlette:
    async def handler(request: Request) -> JSONResponse:
        request.app.state.handler_calls += 1
        request.app.state.handler_started.set()
        await request.app.state.handler_release.wait()
        return JSONResponse({"id": "res-1"}, status_code=201)

    app = Starlette(
        routes=[Route("/api/v1/news", handler, methods=["POST"])],
        middleware=[Middleware(IdempotencyMiddleware)],
    )
    app.state.redis = redis
    app.state.handler_started = asyncio.Event()
    app.state.handler_release = asyncio.Event()
    app.state.handler_calls = 0
    return app


class TestRealRedisIdempotency:
    async def test_inflight_conflict_replay_and_lock_lifecycle(self):
        """Полный lease-жизненный цикл на реальном Redis.

        1. Первый POST с Idempotency-Key берёт лок (SET NX EX) и «зависает»
           в обработчике; лок живой, TTL установлен (>0 — протухнет сам).
        2. Конкурентный POST с тем же ключом → 409 (in-flight), handler не звался.
        3. После завершения первого: 201, лок снят production-release'ом.
        4. Повтор POST → replay 201 c X-Idempotency-Replayed, handler звался 1 раз.
        5. Кэш-запись имеет TTL (setex), а не вечный ключ.
        """
        _skip_if_no_redis()
        redis = await _make_redis()
        session_id = f"itest-{uuid.uuid4().hex[:10]}"
        idem_key = f"key-{uuid.uuid4().hex[:10]}"
        cookies = {"portal_session": session_id}

        async def _post(client: httpx.AsyncClient) -> httpx.Response:
            # cookies живут на клиенте: per-request cookies у httpx deprecated
            # и под CI-фильтрами warnings превращаются в ошибку
            return await client.post(
                "/api/v1/news",
                headers={"Idempotency-Key": idem_key},
            )

        async def _fingerprint_key():
            from app.middleware.idempotency import _request_fingerprint

            fp = _request_fingerprint("POST", "/api/v1/news", b"")
            return (
                f"idempotency:{session_id}:{idem_key}:{fp}",
                f"idempotency_lock:{session_id}:{idem_key}:{fp}",
            )

        try:
            app = _build_app(redis)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test", cookies=cookies
            ) as client:
                first = asyncio.create_task(_post(client))
                await asyncio.wait_for(app.state.handler_started.wait(), timeout=5)

                cache_key, lock_key = await _fingerprint_key()

                # (1) lease живой и с TTL — упавший воркер не заморозит ключ навсегда.
                # TTL-контракт — ЛИТЕРАЛ 120с (review-3, P1: сравнение с
                # импортированной _LOCK_TTL было таутологией — мутация
                # константы 120→1 оставляла тест зелёным). 120 — осознанный
                # выбор lease (см. докстринг _LOCK_TTL: обязан покрывать
                # максимальную длительность защищаемого POST). Осознанное
                # изменение lease = обновить этот литерал вместе с константой.
                assert await redis.exists(lock_key) == 1, "in-flight lock обязан существовать"
                lock_ttl = await redis.ttl(lock_key)
                assert EXPECTED_LOCK_TTL - 10 <= lock_ttl <= EXPECTED_LOCK_TTL, (
                    f"lock TTL={lock_ttl}s, контракт {EXPECTED_LOCK_TTL}s — "
                    "lease урезан или TTL не выставлен"
                )

                # (2) конкурент с тем же ключом — 409, handler не звался повторно
                second = await _post(client)
                assert second.status_code == 409, second.text
                assert app.state.handler_calls == 1

                # (3) отпускаем обработчик → 201, лок снят production-release
                app.state.handler_release.set()
                first_resp = await asyncio.wait_for(first, timeout=5)
                assert first_resp.status_code == 201, first_resp.text
                assert await redis.exists(lock_key) == 0, "лок обязан быть снят после commit"

                # (4) replay без вызова handler
                replay = await _post(client)
                assert replay.status_code == 201
                assert replay.json() == {"id": "res-1"}
                assert replay.headers.get("x-idempotency-replayed") == "true"
                assert app.state.handler_calls == 1, "replay не должен звать handler"

                # (5) кэш с TTL (setex), не вечный
                cache_ttl = await redis.ttl(cache_key)
                assert cache_ttl > 0, f"cache без TTL (ttl={cache_ttl})"
        finally:
            cache_key, lock_key = await _fingerprint_key()
            await redis.delete(cache_key, lock_key)
            await redis.aclose()

    async def test_stale_owner_cannot_release_foreign_lock(self):
        """Takeover-сценарий: лок истёк, перехвачен владельцем B; release от
        старого владельца A НЕ должен удалить лок B (WATCH compare-and-delete).

        Наивный GET→DELETE удалял бы чужой лок и открывал второе исполнение
        операции — это ядро lease-модели (audit-review 2026-08-22, P1),
        проверенное здесь на настоящем WATCH-пути Redis.
        """
        _skip_if_no_redis()
        redis = await _make_redis()
        lock_key = f"idempotency_lock:itest-{uuid.uuid4().hex[:10]}"
        try:
            owner_b = "value-B"
            assert await redis.set(lock_key, owner_b, ex=60, nx=True)

            # старый владелец A пытается снять (его value уже не в ключе)
            await _release_lock_atomic(redis, lock_key, "value-A-stale")
            assert await redis.get(lock_key) == owner_b, (
                "release старым владельцем удалил ЧУЖОЙ лок — WATCH-сломан"
            )

            # настоящий владелец B снимает корректно
            await _release_lock_atomic(redis, lock_key, owner_b)
            assert await redis.exists(lock_key) == 0
        finally:
            await redis.delete(lock_key)
            await redis.aclose()

    @pytest.mark.filterwarnings(
        # redis-py asyncio при WatchError оставляет не-await корутину reset()
        # в недрах execute(); это поведение клиента, не наш код
        "ignore:coroutine 'Pipeline.reset' was never awaited:RuntimeWarning"
    )
    async def test_release_lock_survives_takeover_between_get_and_exec(self):
        """Поведенческий takeover-барьер (review-3, P1; замена MONITOR-теста).

        Контрпример ревью: WATCH-протокол сам по себе не доказывает
        атомарность — реализация может штатно исполнять WATCH→GET→MULTI→DEL,
        но при WatchError ошибочно делать безусловный DELETE. MONITOR-тест
        такого не видел (конфликта нет), stale-owner тест тоже (владелец
        менялся ДО release). Здесь окно создаётся детерминированно:
        перехватывающий клиент подменяет владельца лока РОВНО между GET и
        EXEC production-release (SET через независимое соединение ломает
        WATCH). Контракт: лок нового владельца B обязан остаться живым.

        Ловит все три дефектные реализации: (а) наивный GET→DELETE без
        WATCH, (б) WATCH-протокол с безусловным DELETE при WatchError,
        (в) WATCH-протокол без отмены транзакции. Production проходит.
        """
        from redis.exceptions import WatchError

        _skip_if_no_redis()
        redis = await _make_redis()
        takeover_redis = await _make_redis()
        lock_key = f"idempotency_lock:itest-{uuid.uuid4().hex[:10]}"
        owner_a = "value-A"
        owner_b = "value-B-takeover"
        await redis.set(lock_key, owner_a, ex=60, nx=True)

        class _TakeoverPipeline:
            """Обёртка над pipeline: после GET меняет владельца снаружи."""

            def __init__(self, real, key: str, new_owner: str) -> None:
                self._real = real
                self._key = key
                self._new_owner = new_owner
                self._injected = False

            def watch(self, key):
                return self._real.watch(key)

            async def get(self, key):
                value = await self._real.get(key)
                if key == self._key and not self._injected:
                    self._injected = True
                    # ТОЧКА TAKEOVER: ключ уже прочитан владельцем A, транзакция
                    # ещё не EXEC'нута — независимый клиент перехватывает лок.
                    await takeover_redis.set(self._key, self._new_owner)
                return value

            def multi(self):
                return self._real.multi()

            def delete(self, key):
                return self._real.delete(key)

            async def execute(self):
                return await self._real.execute()

            async def unwatch(self):
                return self._real.unwatch()

            async def reset(self):
                return self._real.reset()

        class _TakeoverRedis:
            def __init__(self, inner, key: str, new_owner: str) -> None:
                self._inner = inner
                self._key = key
                self._new_owner = new_owner

            def pipeline(self, transaction=True):
                return _TakeoverPipeline(
                    self._inner.pipeline(transaction=transaction), self._key, self._new_owner
                )

        interceptor = _TakeoverRedis(redis, lock_key, owner_b)
        try:
            # правильная реализация: EXEC отменён WATCH-конфликтом и поднимает
            # WatchError — именно это production и обязан делать
            with contextlib.suppress(WatchError):
                await _release_lock_atomic(interceptor, lock_key, owner_a)

            survivor = await redis.get(lock_key)
            assert survivor == owner_b, (
                f"release снял ЧУЖОЙ лок при takeover между GET и EXEC "
                f"(в ключе: {survivor!r}) — атомарность сломана"
            )
        finally:
            await redis.delete(lock_key)
            await redis.aclose()
            await takeover_redis.aclose()
