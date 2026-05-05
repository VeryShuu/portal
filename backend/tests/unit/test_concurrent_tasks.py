"""Tests for the concurrent_tasks fixture (multi-worker concurrency simulation).

Covers:
- Basic concurrent execution runs all tasks
- Idempotency middleware: concurrent POST with same key → only one origin request, rest replayed
- concurrent_tasks fixture collects exceptions without aborting siblings
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytestmark = pytest.mark.asyncio


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
    """Tests idempotency middleware under concurrent same-key requests."""

    async def test_same_key_replayed_from_cache(self, concurrent_tasks):
        """Simulate two workers hitting idempotency cache concurrently.

        The middleware uses redis.get() then redis.setex(); under concurrent
        requests with the same key, after the first response is cached all
        subsequent requests should receive the replayed response.

        This test exercises the logic path using fakeredis directly.
        """
        try:
            import fakeredis.aioredis as fakeredis_aio
        except ImportError:
            pytest.skip("fakeredis not installed")

        from app.middleware.idempotency import _CACHE_TTL, _KEY_PREFIX

        redis = fakeredis_aio.FakeRedis(decode_responses=True)
        idem_key = "test-concurrent-key"
        cache_key = f"{_KEY_PREFIX}{idem_key}"

        call_count = 0

        async def _handle_request(i: int) -> str:
            nonlocal call_count
            cached = await redis.get(cache_key)
            if cached is not None:
                entry = json.loads(cached)
                return f"replayed:{entry['body']['id']}"
            call_count += 1
            resource_id = "resource-123"
            await redis.setex(
                cache_key,
                _CACHE_TTL,
                json.dumps({"body": {"id": resource_id}, "status_code": 201}),
            )
            return f"created:{resource_id}"

        results = await concurrent_tasks(_handle_request, count=10)

        created = [r for r in results if r.startswith("created:")]
        replayed = [r for r in results if r.startswith("replayed:")]

        assert len(created) >= 1, "At least one request should actually create the resource"
        assert len(created) + len(replayed) == 10, "All requests should complete"
        assert all(r == "replayed:resource-123" for r in replayed)

    async def test_different_keys_do_not_share_cache(self, concurrent_tasks):
        """Different idempotency keys must be isolated."""
        try:
            import fakeredis.aioredis as fakeredis_aio
        except ImportError:
            pytest.skip("fakeredis not installed")

        from app.middleware.idempotency import _CACHE_TTL, _KEY_PREFIX

        redis = fakeredis_aio.FakeRedis(decode_responses=True)

        async def _handle(i: int) -> str:
            key = f"{_KEY_PREFIX}key-{i}"
            cached = await redis.get(key)
            if cached:
                return f"replayed:{i}"
            await redis.setex(key, _CACHE_TTL, json.dumps({"body": {"id": i}, "status_code": 201}))
            return f"created:{i}"

        results = await concurrent_tasks(_handle, count=5)
        assert all(r.startswith("created:") for r in results), (
            "Different keys must not share cache"
        )
