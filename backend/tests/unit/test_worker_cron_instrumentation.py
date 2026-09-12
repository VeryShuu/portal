"""PA-021: cron-задачи воркера обязаны попадать в ARQ job-метрики.

Прежде cron-декларации использовали строковую форму cron("<fqn>"): ARQ
резолвил raw-coroutine и исполнял её под именем 'cron:<fqn>' — мимо
track_arq_job. Scheduled-прогоны (audit flush, outbox-диспетчер, helpdesk
poller, ERP sync...) не увеличивали portal_arq_jobs_total, и падения cron
не могли зажечь PortalArqJobFailures.

Контракт:
- каждая cron-задача WorkerSettings.cron_jobs имеет tooling-обёртку
  (__wrapped__), КРОМЕ сборщиков метрик/heartbeat (_CRON_UNINSTRUMENTED);
- имя регистрации сохраняется ('cron:<fqn>') — реестр/уникальность ARQ
  не меняются;
- реальное исполнение обёрнутой cron-корутины пишет arq:metrics:jobs /
  arq:metrics:job_ms (те же серии, что у ручных enqueue).

Контрпример-валидация: перевести любую tracked_cron(...) обратно в
cron(...) → test_all_cron_jobs_are_instrumented падает.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("arq")
pytest.importorskip("fakeredis")

from app.worker.main import _CRON_UNINSTRUMENTED, WorkerSettings, tracked_cron

ARQ_JOBS_KEY = "arq:metrics:jobs"
ARQ_JOB_TIME_KEY = "arq:metrics:job_ms"


class TestCronInstrumentationRegistry:
    def test_all_cron_jobs_are_instrumented(self):
        """Каждая cron-задача обёрнута track_arq_job, кроме исключений."""
        excluded_names = {f"cron:{fqn}" for fqn in _CRON_UNINSTRUMENTED}
        bare: list[str] = []
        for job in WorkerSettings.cron_jobs:
            wrapped = getattr(job.coroutine, "__wrapped__", None) is not None
            if job.name in excluded_names:
                if wrapped:
                    pytest.fail(f"исключённая cron-задача обёрнута: {job.name}")
                continue
            if not wrapped:
                bare.append(job.name)
        assert not bare, (
            "cron-задачи без track_arq_job (не попадут в job-метрики/alert): " + ", ".join(bare)
        )

    def test_registry_names_keep_cron_prefix(self):
        """Имена регистрации остаются 'cron:<fqn>' — семантика ARQ не менялась."""
        for job in WorkerSettings.cron_jobs:
            assert job.name.startswith("cron:"), job.name

    def test_excluded_collectors_present(self):
        """Сами сборщики метрик/heartbeat зарегистрированы и НЕ обёрнуты."""
        names = {job.name for job in WorkerSettings.cron_jobs}
        for fqn in _CRON_UNINSTRUMENTED:
            assert f"cron:{fqn}" in names


class TestTrackedCronExecution:
    async def test_wrapped_cron_execution_writes_metrics(self):
        """Исполнение cron-корутины из tracked_cron пишет started/succeeded/duration."""
        from fakeredis.aioredis import FakeRedis

        job = tracked_cron("tests.unit._pa021_dummy.dummy_cron_task", minute=None, second=0)
        assert job.name == "cron:tests.unit._pa021_dummy.dummy_cron_task"
        assert getattr(job.coroutine, "__wrapped__", None) is not None

        redis = FakeRedis(decode_responses=True)
        ctx: dict[str, Any] = {"redis": redis}
        result = await job.coroutine(ctx)  # то же, что делает Worker при scheduled-прогоне
        assert result == "ok"

        assert int(await redis.hget(ARQ_JOBS_KEY, "dummy_cron_task:started")) == 1
        assert int(await redis.hget(ARQ_JOBS_KEY, "dummy_cron_task:succeeded")) == 1
        assert int(await redis.hget(ARQ_JOB_TIME_KEY, "dummy_cron_task:count")) == 1
        assert int(await redis.hget(ARQ_JOB_TIME_KEY, "dummy_cron_task:sum")) >= 0

    async def test_wrapped_cron_failure_records_failed_status(self):
        """Падение cron-исполнения фиксируется статусом failed (путь до alert)."""
        from fakeredis.aioredis import FakeRedis

        job = tracked_cron("tests.unit._pa021_dummy.failing_cron_task")
        redis = FakeRedis(decode_responses=True)
        with pytest.raises(RuntimeError):
            await job.coroutine({"redis": redis})
        assert int(await redis.hget(ARQ_JOBS_KEY, "failing_cron_task:started")) == 1
        assert int(await redis.hget(ARQ_JOBS_KEY, "failing_cron_task:failed")) == 1
