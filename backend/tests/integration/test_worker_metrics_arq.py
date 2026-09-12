"""Real ARQ lifecycle on run-scoped Redis keys; never FLUSHDB."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from arq.connections import ArqRedis, RedisSettings, create_pool
from arq.cron import cron
from arq.worker import Worker, func

from app.core.config import get_settings
from app.worker.tasks import integration_health, metrics


@pytest.fixture
async def arq_scope(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[ArqRedis, str]]:
    if os.environ.get("INTEGRATION_REDIS", "false").lower() not in {"1", "true", "yes"}:
        pytest.skip("INTEGRATION_REDIS=true required")
    scope = "mon02-" + uuid.uuid4().hex
    settings = RedisSettings.from_dsn(get_settings().redis_url)
    pool = await create_pool(settings)
    monkeypatch.setattr(metrics, "ARQ_JOBS_KEY", scope + ":metrics:jobs")
    monkeypatch.setattr(metrics, "ARQ_JOB_TIME_KEY", scope + ":metrics:duration")
    try:
        yield pool, scope
    finally:
        # Worker.close() may have closed its pool. A fresh client owns cleanup.
        cleanup = await create_pool(settings)
        try:
            keys = [key async for key in cleanup.scan_iter(match=f"*{scope}*")]
            if keys:
                await cleanup.delete(*keys)
        finally:
            await cleanup.aclose()
            await pool.aclose()


@pytest.mark.parametrize("scheduled", [False, True], ids=["enqueued", "cron-zero-retention"])
async def test_real_arq_deadline_is_not_success(arq_scope, scheduled: bool) -> None:
    pool, scope = arq_scope

    @metrics.track_arq_job
    async def slow_task(ctx: dict[str, Any]) -> None:
        await asyncio.Event().wait()

    name = scope + ":slow"
    worker = Worker(
        functions=[] if scheduled else [func(slow_task, name=name, timeout=0.05)],  # type: ignore[arg-type]
        cron_jobs=[
            cron(slow_task, name=name, timeout=0.05, run_at_startup=True, keep_result=0)  # type: ignore[arg-type]
        ]
        if scheduled
        else None,
        redis_pool=pool,
        queue_name=scope,
        burst=True,
        max_burst_jobs=1,
        handle_signals=False,
        poll_delay=0.01,
    )
    if not scheduled:
        await pool.enqueue_job(name, _queue_name=scope, _job_id=scope + ":job")
    await asyncio.wait_for(worker.async_run(), timeout=5)
    assert worker.jobs_failed == 1  # ARQ observes the outer TimeoutError.
    assert await pool.hgetall(metrics.ARQ_JOBS_KEY) == {
        b"slow_task:started": b"1",
        b"slow_task:cancelled": b"1",
    }
    assert await pool.hget(metrics.ARQ_JOB_TIME_KEY, "slow_task:count") == b"1"


async def test_real_arq_cancellation_retries_then_succeeds(arq_scope) -> None:
    pool, scope = arq_scope
    started = asyncio.Event()
    attempts: list[int] = []

    @metrics.track_arq_job
    async def interrupted(ctx: dict[str, Any]) -> str:
        attempts.append(ctx["job_try"])
        if ctx["job_try"] == 1:
            started.set()
            await asyncio.Event().wait()
        return "ok"

    name, job_id = scope + ":retry", scope + ":job"
    first_worker = Worker(
        functions=[func(interrupted, name=name, timeout=10)],  # type: ignore[arg-type]
        redis_pool=pool,
        queue_name=scope,
        burst=True,
        max_burst_jobs=1,
        handle_signals=False,
        poll_delay=0.01,
    )
    run = None
    try:
        await pool.enqueue_job(name, _queue_name=scope, _job_id=job_id)
        run = asyncio.create_task(first_worker.async_run())
        await asyncio.wait_for(started.wait(), timeout=5)
        first_worker.job_tasks[job_id].cancel()
        await asyncio.wait_for(run, timeout=5)

        # A burst worker exits after consuming its one job, including a retry.
        # A fresh worker invocation proves that ARQ persisted and re-runs the
        # cancelled attempt instead of treating the interruption as success.
        retry_worker = Worker(
            functions=[func(interrupted, name=name, timeout=10)],  # type: ignore[arg-type]
            redis_pool=pool,
            queue_name=scope,
            burst=True,
            max_burst_jobs=1,
            handle_signals=False,
            poll_delay=0.01,
        )
        await asyncio.wait_for(retry_worker.async_run(), timeout=5)
        assert attempts == [1, 2]
        assert first_worker.jobs_retried == 1
        assert retry_worker.jobs_complete == 1
        assert await pool.hgetall(metrics.ARQ_JOBS_KEY) == {
            b"interrupted:started": b"2",
            b"interrupted:cancelled": b"1",
            b"interrupted:succeeded": b"1",
        }
        assert await pool.hget(metrics.ARQ_JOB_TIME_KEY, "interrupted:count") == b"2"
    finally:
        if run is not None and not run.done():
            run.cancel()
            await asyncio.gather(run, return_exceptions=True)


async def test_real_arq_structured_failure_keeps_completion_semantics(arq_scope) -> None:
    """ARQ completes the job while monitoring records its business failure."""
    pool, scope = arq_scope
    task_result = {"error": "upstream unavailable"}

    @metrics.track_arq_job
    async def result_failed_task(ctx: dict[str, Any]) -> dict[str, str]:
        return task_result

    name = scope + ":result-failed"
    worker = Worker(
        functions=[func(result_failed_task, name=name)],  # type: ignore[arg-type]
        redis_pool=pool,
        queue_name=scope,
        burst=True,
        max_burst_jobs=1,
        handle_signals=False,
        poll_delay=0.01,
    )
    await pool.enqueue_job(name, _queue_name=scope, _job_id=scope + ":result-job")
    await asyncio.wait_for(worker.async_run(), timeout=5)

    assert worker.jobs_complete == 1
    assert worker.jobs_failed == 0
    assert await pool.hgetall(metrics.ARQ_JOBS_KEY) == {
        b"result_failed_task:started": b"1",
        b"result_failed_task:result_failed": b"1",
    }


async def test_integration_probe_atomically_replaces_disabled_fields(
    arq_scope, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, scope = arq_scope
    key = scope + ":integration-health"
    state_key = scope + ":integration-probe-state"
    monkeypatch.setattr(integration_health, "INTEGRATION_HEALTH_KEY", key)
    monkeypatch.setattr(
        integration_health,
        "INTEGRATION_PROBE_STATE_KEY",
        state_key,
    )

    probe_names = (
        "_probe_keycloak",
        "_probe_nextcloud",
        "_probe_smtp",
        "_probe_collabora",
        "_probe_erp_sync",
        "_probe_erp_absences",
        "_probe_directum",
        "_probe_erp_approvals",
    )
    probes = {name: AsyncMock(return_value=None) for name in probe_names}
    for name, probe in probes.items():
        monkeypatch.setattr(integration_health, name, probe)

    probes["_probe_keycloak"].return_value = False
    probes["_probe_nextcloud"].return_value = True
    await integration_health.probe_integrations({"redis": pool})
    assert await pool.hgetall(key) == {b"keycloak": b"0", b"nextcloud": b"1"}
    state = await pool.hgetall(state_key)
    assert state[b"keycloak:expected"] == b"1"
    assert state[b"keycloak:result"] == b"0"
    assert state[b"nextcloud:result"] == b"1"
    assert await pool.ttl(state_key) == -1

    probes["_probe_keycloak"].return_value = None
    await integration_health.probe_integrations({"redis": pool})
    assert await pool.hgetall(key) == {b"nextcloud": b"1"}
    state = await pool.hgetall(state_key)
    assert state[b"keycloak:expected"] == b"0"
    assert b"keycloak:result" not in state
    assert b"keycloak:last_completed" in state

    probes["_probe_nextcloud"].return_value = None
    await integration_health.probe_integrations({"redis": pool})
    assert await pool.exists(key) == 0
    state = await pool.hgetall(state_key)
    assert state[b"keycloak:expected"] == b"0"
    assert state[b"nextcloud:expected"] == b"0"
    assert not any(field.endswith(b":result") for field in state)
