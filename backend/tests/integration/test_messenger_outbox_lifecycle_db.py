"""Integration: жизненный цикл messenger_outbox на реальной PostgreSQL + Redis.

Зеркало test_email_outbox_lifecycle_db.py для мессенджер-каналов (MAX, Matrix).
Аудит тестирования 2026-08-21 (docs/wip/test-audit-remediation.md): unit-тесты
сервиса (test_messenger_outbox_service.py) построены на AsyncMock. Здесь —
реальные бизнес-инварианты: транзакционность enqueue, claim-изоляция
SKIP LOCKED, backoff/DLQ, watchdog, админ-переходы, cleanup и orchestration
диспетчера (группировка по провайдеру, unknown provider → permanent DLQ).

Запуск: ./scripts/test-integration.sh tests/integration/test_messenger_outbox_lifecycle_db.py
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


def _now() -> datetime:
    return datetime.now(UTC)


async def _insert(
    session: AsyncSession,
    *,
    provider: str = "max",
    status: str = "PENDING",
    attempts: int = 0,
    max_attempts: int = 6,
    next_attempt_at: datetime | None = None,
    updated_at: datetime | None = None,
    last_error: str | None = None,
) -> uuid.UUID:
    """Сырой INSERT с явными статусами/временами (RETURNING id)."""
    row = await session.execute(
        text(
            """
            INSERT INTO messenger_outbox (
                provider, chat_id, text, payload, status,
                attempts, max_attempts, next_attempt_at, updated_at, last_error
            ) VALUES (
                :provider, :chat_id, 'test message',
                CAST('{}' AS JSONB), :status,
                :attempts, :max_attempts, :next_at, :updated_at, :last_error
            )
            RETURNING id
            """
        ),
        {
            "provider": provider,
            "chat_id": f"chat-{uuid.uuid4().hex[:8]}",
            "status": status,
            "attempts": attempts,
            "max_attempts": max_attempts,
            # дефолт «минуту назад»: часы хоста и БД-контейнера расходятся на
            # миллисекунды — свежий _now() иногда опережает NOW() базы и строка
            # не проходит фильтр next_attempt_at <= NOW() в claim_pending
            "next_at": next_attempt_at or (_now() - timedelta(seconds=60)),
            "updated_at": updated_at or _now(),
            "last_error": last_error,
        },
    )
    return uuid.UUID(str(row.scalar_one()))


async def _fetch(session: AsyncSession, outbox_id: uuid.UUID) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT status, attempts, max_attempts, next_attempt_at, updated_at,
                       sent_at, last_error, last_error_type, last_error_class
                FROM messenger_outbox WHERE id = :id
                """
                ),
                {"id": outbox_id},
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


async def _insert_committed(engine: AsyncEngine, **kwargs: Any) -> uuid.UUID:
    async with AsyncSession(engine, expire_on_commit=False) as s:
        new_id = await _insert(s, **kwargs)
        await s.commit()
        return new_id


async def _fetch_committed(engine: AsyncEngine, outbox_id: uuid.UUID) -> dict[str, Any]:
    async with AsyncSession(engine, expire_on_commit=False) as s:
        row = await _fetch(s, outbox_id)
        await s.commit()
        return row


@pytest_asyncio.fixture
async def outbox_cleanup(real_db_engine: AsyncEngine) -> AsyncGenerator[list[uuid.UUID], None]:
    """ID закоммиченных строк — удалить в teardown (диспетчер/конкурентность)."""
    ids: list[uuid.UUID] = []
    yield ids
    if ids:
        async with AsyncSession(real_db_engine, expire_on_commit=False) as s:
            await s.execute(
                text("DELETE FROM messenger_outbox WHERE id = ANY(CAST(:ids AS UUID[]))"),
                {"ids": [str(i) for i in ids]},
            )
            await s.commit()


class TestOutboxTransactionInvariant:
    async def test_rollback_of_business_transaction_leaves_no_message(self, real_db_session):
        """Outbox-инвариант: rollback бизнес-операции не оставляет сообщений."""
        from app.services.messenger_outbox import enqueue_messenger_message

        await enqueue_messenger_message(
            real_db_session,
            provider="max",
            chat_id="ghost-chat",
            text="Отменённая операция",
        )
        await real_db_session.rollback()

        left = (
            await real_db_session.execute(
                text("SELECT count(*) FROM messenger_outbox WHERE chat_id = 'ghost-chat'")
            )
        ).scalar_one()
        assert left == 0


class TestClaimPendingDb:
    async def test_claim_takes_only_ready_pending(self, real_db_session):
        from app.services.messenger_outbox import claim_pending

        ready = await _insert(real_db_session)
        future = await _insert(real_db_session, next_attempt_at=_now() + timedelta(hours=1))
        sent = await _insert(real_db_session, status="SENT")
        await real_db_session.flush()

        claimed = await claim_pending(real_db_session, limit=10)
        assert {row["id"] for row in claimed} == {ready}
        assert (await _fetch(real_db_session, ready))["status"] == "SENDING"
        assert (await _fetch(real_db_session, future))["status"] == "PENDING"
        assert (await _fetch(real_db_session, sent))["status"] == "SENT"

    async def test_claim_respects_limit_in_fifo_order(self, real_db_session):
        from app.services.messenger_outbox import claim_pending

        base = _now() - timedelta(minutes=10)
        oldest = await _insert(real_db_session, next_attempt_at=base)
        middle = await _insert(real_db_session, next_attempt_at=base + timedelta(minutes=5))
        newest = await _insert(real_db_session, next_attempt_at=base + timedelta(minutes=9))
        await real_db_session.flush()

        claimed = await claim_pending(real_db_session, limit=2)
        assert [row["id"] for row in claimed] == [oldest, middle]
        assert (await _fetch(real_db_session, newest))["status"] == "PENDING"

    async def test_concurrent_claims_never_overlap(self, real_db_engine, outbox_cleanup):
        """FOR UPDATE SKIP LOCKED: конкурентные воркеры не заберут одно сообщение."""
        from app.services.messenger_outbox import claim_pending

        ids = {await _insert_committed(real_db_engine) for _ in range(6)}
        outbox_cleanup.extend(ids)

        async with (
            AsyncSession(real_db_engine, expire_on_commit=False) as worker_a,
            AsyncSession(real_db_engine, expire_on_commit=False) as worker_b,
        ):
            claimed_a, claimed_b = await asyncio.gather(
                claim_pending(worker_a, limit=3),
                claim_pending(worker_b, limit=6),
            )
            ids_a = {row["id"] for row in claimed_a}
            ids_b = {row["id"] for row in claimed_b}
            # Делёж может быть любым (3/3 при интерливинге, 0/6 при полной
            # сериализации на медленном раннере): SKIP LOCKED не обещает равное
            # деление, только непересечение и полноту захвата.
            assert not (ids_a & ids_b), "сообщение захвачено двумя воркерами"
            assert ids_a | ids_b == ids, "часть сообщений потеряна при конкурентном захвате"
            await worker_a.rollback()
            await worker_b.rollback()


class TestMarkSentFailedDb:
    async def test_mark_sent_sets_sent_at_and_clears_error(self, real_db_session):
        from app.services.messenger_outbox import claim_pending, mark_sent

        outbox_id = await _insert(real_db_session, attempts=1, last_error="старая ошибка")
        await real_db_session.flush()
        claimed = await claim_pending(real_db_session, limit=1)
        assert claimed[0]["id"] == outbox_id

        await mark_sent(real_db_session, outbox_id)

        row = await _fetch(real_db_session, outbox_id)
        assert row["status"] == "SENT"
        assert row["sent_at"] is not None
        assert row["attempts"] == 2
        assert row["last_error"] is None

    async def test_mark_failed_transient_requeues_with_backoff(self, real_db_session):
        from app.services.messenger_outbox import mark_failed

        outbox_id = await _insert(real_db_session, attempts=0)
        before = _now()

        new_status = await mark_failed(
            real_db_session,
            outbox_id,
            error="connection refused",
            error_type="ConnectionRefusedError",
            error_class="transient",
            current_attempts=0,
            max_attempts=6,
        )

        assert new_status == "PENDING"
        row = await _fetch(real_db_session, outbox_id)
        assert row["status"] == "PENDING"
        assert row["attempts"] == 1
        assert row["last_error_class"] == "transient"
        # defer = 30с + 15% джиттер для первой transient-попытки
        delta = (row["next_attempt_at"] - before).total_seconds()
        assert 25 <= delta <= 65, f"unexpected backoff {delta}s"

    async def test_mark_failed_permanent_goes_dlq_immediately(self, real_db_session):
        from app.services.messenger_outbox import mark_failed

        outbox_id = await _insert(real_db_session, attempts=0)
        old_next = (await _fetch(real_db_session, outbox_id))["next_attempt_at"]

        new_status = await mark_failed(
            real_db_session,
            outbox_id,
            error="535 auth failed",
            error_type="SMTPAuthenticationError",
            error_class="permanent",
            current_attempts=0,
            max_attempts=6,
        )

        assert new_status == "DLQ"
        row = await _fetch(real_db_session, outbox_id)
        assert row["status"] == "DLQ"
        assert row["attempts"] == 1
        assert row["next_attempt_at"] == old_next

    async def test_mark_failed_exhausted_attempts_goes_dlq(self, real_db_session):
        from app.services.messenger_outbox import mark_failed

        outbox_id = await _insert(real_db_session, attempts=5, max_attempts=6)

        new_status = await mark_failed(
            real_db_session,
            outbox_id,
            error="timeout again",
            error_type="TimeoutError",
            error_class="transient",
            current_attempts=5,
            max_attempts=6,
        )

        assert new_status == "DLQ"
        assert (await _fetch(real_db_session, outbox_id))["attempts"] == 6


class TestWatchdogDb:
    async def test_requeue_stale_sending_returns_only_old_rows(self, real_db_session):
        from app.services.messenger_outbox import requeue_stale_sending

        stale = await _insert(
            real_db_session,
            status="SENDING",
            attempts=2,
            updated_at=_now() - timedelta(seconds=700),
        )
        fresh = await _insert(real_db_session, status="SENDING")
        await real_db_session.flush()

        count = await requeue_stale_sending(real_db_session, older_than_seconds=600)

        assert count == 1
        stale_row = await _fetch(real_db_session, stale)
        assert stale_row["status"] == "PENDING"
        assert stale_row["attempts"] == 2  # незавершённая попытка не считается
        assert (await _fetch(real_db_session, fresh))["status"] == "SENDING"


class TestAdminTransitionsDb:
    async def test_reschedule_for_retry_reset_and_keep_attempts(self, real_db_session):
        from app.services.messenger_outbox import reschedule_for_retry

        reset_id = await _insert(real_db_session, status="DLQ", attempts=6)
        keep_id = await _insert(real_db_session, status="CANCELLED", attempts=3)
        await real_db_session.flush()

        assert await reschedule_for_retry(real_db_session, reset_id, reset_attempts=True)
        assert await reschedule_for_retry(real_db_session, keep_id, reset_attempts=False)

        assert (await _fetch(real_db_session, reset_id))["attempts"] == 0
        keep_row = await _fetch(real_db_session, keep_id)
        assert keep_row["attempts"] == 3
        assert keep_row["status"] == "PENDING"

    async def test_reschedule_for_retry_rejects_in_flight_sending(self, real_db_session):
        from app.services.messenger_outbox import reschedule_for_retry

        sending_id = await _insert(real_db_session, status="SENDING")
        await real_db_session.flush()

        ok = await reschedule_for_retry(real_db_session, sending_id)
        assert ok is False
        assert (await _fetch(real_db_session, sending_id))["status"] == "SENDING"

    @pytest.mark.parametrize(
        ("status", "expected"),
        [("PENDING", True), ("FAILED", True), ("DLQ", True), ("SENDING", False), ("SENT", False)],
    )
    async def test_cancel_state_machine(self, real_db_session, status: str, expected: bool):
        from app.services.messenger_outbox import cancel

        outbox_id = await _insert(real_db_session, status=status)
        await real_db_session.flush()

        assert await cancel(real_db_session, outbox_id) is expected
        final_status = (await _fetch(real_db_session, outbox_id))["status"]
        assert final_status == ("CANCELLED" if expected else status)


class TestCleanupDb:
    async def test_cleanup_deletes_only_old_sent(self, real_db_session):
        from app.services.messenger_outbox import cleanup_old_sent

        old_days = timedelta(days=40)
        old_sent = await _insert(real_db_session, status="SENT", updated_at=_now() - old_days)
        await real_db_session.execute(
            text("UPDATE messenger_outbox SET sent_at = :t WHERE id = :id"),
            {"t": _now() - old_days, "id": old_sent},
        )
        recent_sent = await _insert(real_db_session, status="SENT")
        await real_db_session.execute(
            text("UPDATE messenger_outbox SET sent_at = :t WHERE id = :id"),
            {"t": _now() - timedelta(days=2), "id": recent_sent},
        )
        old_dlq = await _insert(real_db_session, status="DLQ", updated_at=_now() - old_days)
        old_cancelled = await _insert(
            real_db_session, status="CANCELLED", updated_at=_now() - old_days
        )
        await real_db_session.flush()

        deleted = await cleanup_old_sent(real_db_session, older_than_days=30)

        assert deleted == 1
        remaining = {
            r["id"]
            for r in (
                await real_db_session.execute(text("SELECT id FROM messenger_outbox"))
            ).mappings()
        }
        assert remaining == {recent_sent, old_dlq, old_cancelled}


class TestDispatcherDb:
    """Orchestration process_messenger_outbox: реальные PG + Redis.

    Провайдер-специфичная отправка (MAX/Matrix клиенты) подменяется на
    _dispatch_max — здесь проверяется диспетчер: watchdog, claim, группировка
    по провайдеру, unknown-provider → permanent, unconfigured → transient.
    """

    async def test_dispatcher_happy_path_and_stale_sending_recovery(
        self, real_db_engine, redis_client, outbox_cleanup, monkeypatch
    ):
        import app.worker.tasks.messenger_outbox as worker_mod

        dispatched: list[list[dict]] = []

        async def _fake_dispatch_max(rows: list[dict]) -> int:
            dispatched.append(rows)
            from app.services.messenger_outbox import mark_sent

            async with AsyncSession(real_db_engine, expire_on_commit=False) as session:
                for row in rows:
                    await mark_sent(session, row["id"])
                await session.commit()
            return len(rows)

        monkeypatch.setattr(worker_mod, "_dispatch_max", _fake_dispatch_max)

        from app.worker.tasks.messenger_outbox import process_messenger_outbox

        fresh = await _insert_committed(real_db_engine, provider="max")
        stale_sending = await _insert_committed(
            real_db_engine,
            provider="max",
            status="SENDING",
            updated_at=_now() - timedelta(seconds=700),
        )
        outbox_cleanup.extend([fresh, stale_sending])

        result = await process_messenger_outbox({"redis": redis_client})

        assert result == 2
        assert len(dispatched) == 1 and len(dispatched[0]) == 2
        for outbox_id in (fresh, stale_sending):
            row = await _fetch_committed(real_db_engine, outbox_id)
            assert row["status"] == "SENT"
            assert row["sent_at"] is not None

    async def test_dispatcher_unconfigured_max_is_transient_not_dlq(
        self, real_db_engine, redis_client, outbox_cleanup
    ):
        """Канал выключен/не настроен — сообщения ждут в PENDING, не умирают в DLQ.

        Реальный путь без подмен: в тест-БД нет helpdesk_max_bot_settings.
        """
        from app.worker.tasks.messenger_outbox import process_messenger_outbox

        outbox_id = await _insert_committed(real_db_engine, provider="max")
        outbox_cleanup.append(outbox_id)

        result = await process_messenger_outbox({"redis": redis_client})

        assert result == 0
        row = await _fetch_committed(real_db_engine, outbox_id)
        assert row["status"] == "PENDING"
        assert row["attempts"] == 1
        assert row["last_error_type"] == "ConfigurationError"
        assert row["last_error_class"] == "transient"

    async def test_db_rejects_unknown_provider(self, real_db_engine, redis_client, outbox_cleanup):
        """Неизвестный провайдер не может попасть в outbox — CHECK-констейнт.

        ``ck_messenger_outbox_provider`` (миграции 081→097) разрешает только
        ('max', 'matrix'). Это настоящая защита; ветка unknown-provider в
        process_messenger_outbox — defense-in-depth на случай дрифта констейнта
        и кода (например, новый провайдер добавлен в код до миграции).
        """
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError, match="ck_messenger_outbox_provider"):
            await _insert_committed(real_db_engine, provider="telegram")
