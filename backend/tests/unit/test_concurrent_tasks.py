"""Tests for the concurrent_tasks fixture (multi-worker concurrency simulation).

Covers:
- Basic concurrent execution runs all tasks
- IdempotencyMiddleware: concurrent POST with same key → exactly one origin call
- concurrent_tasks fixture collects exceptions without aborting siblings
"""

from __future__ import annotations

import asyncio

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.middleware.idempotency import IdempotencyMiddleware


class TestConcurrentTasksFixture:
    async def test_runs_all_tasks(self, concurrent_tasks):
        results = await concurrent_tasks(lambda i: asyncio.sleep(0, result=i), count=5)
        assert results == [0, 1, 2, 3, 4]

    async def test_collects_exceptions_without_aborting(self, concurrent_tasks):
        async def _maybe_raise(i: int):
            if i % 2 == 0:
                raise ValueError(f"worker {i} failed")
            return i

        results = await concurrent_tasks(_maybe_raise, count=4)
        errors = [r for r in results if isinstance(r, ValueError)]
        successes = [r for r in results if not isinstance(r, Exception)]
        assert len(errors) == 2
        assert len(successes) == 2

    async def test_concurrent_execution(self, concurrent_tasks):
        """Verify tasks actually run concurrently (not sequentially)."""
        started_at: list[float] = []
        done_at: list[float] = []

        async def _timed(i: int):
            loop = asyncio.get_event_loop()
            started_at.append(loop.time())
            await asyncio.sleep(0.01)
            done_at.append(loop.time())
            return i

        results = await concurrent_tasks(_timed, count=4)
        assert results == [0, 1, 2, 3]
        total_sequential = 4 * 0.01
        actual_elapsed = max(done_at) - min(started_at)
        assert actual_elapsed < total_sequential * 0.9, (
            f"Tasks ran sequentially: elapsed={actual_elapsed:.3f}s "
            f"vs sequential={total_sequential:.3f}s"
        )


class TestIdempotencyMiddlewareConcurrency:
    """Конкурентные POST через настоящий IdempotencyMiddleware (fake Redis).

    Контракт (app/middleware/idempotency.py): при конкурентных POST с одним
    Idempotency-Key origin-обработчик выполняется РОВНО один раз; запросы,
    пришедшие пока обработка идёт, получают 409; после записи кэша — replay
    с X-Idempotency-Replayed. Последовательный replay-контракт покрыт в
    test_idempotency_middleware.py — здесь только конкурентность.
    """

    @staticmethod
    def _build_client(handler) -> httpx.AsyncClient:
        import fakeredis.aioredis as fakeredis_aio
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.routing import Route

        routes = [Route("/api/v1/news", handler, methods=["POST"])]
        app = Starlette(routes=routes, middleware=[Middleware(IdempotencyMiddleware)])
        app.state.redis = fakeredis_aio.FakeRedis(decode_responses=True)
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    async def test_same_key_concurrent_single_origin_execution(self):
        """8 конкурентных POST с одним ключом → ровно один вызов origin.

        Остальные ответы — 409 (in-flight) либо replay из кэша; вариант
        «несколько origin-вызовов» контрактом запрещён.
        """
        call_count = {"n": 0}

        async def handler(request: Request) -> Response:
            call_count["n"] += 1
            # Окно in-flight: пока первый запрос обрабатывается, конкуренты
            # должны наткнуться на lock и получить 409, а не выполнить origin.
            await asyncio.sleep(0.05)
            return JSONResponse({"id": "res-1"}, status_code=201)

        async with self._build_client(handler) as client:
            responses = await asyncio.gather(
                *(
                    client.post("/api/v1/news", headers={"Idempotency-Key": "conc-1"})
                    for _ in range(8)
                )
            )

        assert call_count["n"] == 1, "origin-обработчик обязан выполниться ровно один раз"
        for r in responses:
            assert r.status_code in (201, 409), f"unexpected status {r.status_code}"
        created = [r for r in responses if r.status_code == 201]
        assert created, "хотя бы один запрос должен дойти до origin"
        assert all(r.json() == {"id": "res-1"} for r in created)
        # среди 201-х ровно один живой origin-ответ — без replay-заголовка
        assert sum(1 for r in created if "x-idempotency-replayed" not in r.headers) == 1

    async def test_different_keys_do_not_share_cache(self):
        """Different idempotency keys must be isolated."""
        call_count = {"n": 0}

        async def handler(request: Request) -> Response:
            call_count["n"] += 1
            n = call_count["n"]
            await asyncio.sleep(0.05)
            return JSONResponse({"id": f"res-{n}"}, status_code=201)

        async with self._build_client(handler) as client:
            responses = await asyncio.gather(
                *(
                    client.post("/api/v1/news", headers={"Idempotency-Key": f"key-{i}"})
                    for i in range(5)
                )
            )

        assert call_count["n"] == 5
        assert all(r.status_code == 201 for r in responses)
        assert len({r.json()["id"] for r in responses}) == 5
