"""Integration: жизненный цикл email_outbox на реальной PostgreSQL + Redis.

Аудит тестирования 2026-08-21 (docs/wip/test-audit-remediation.md, фаза
«модули по прод-риску»): unit-тесты сервиса (test_email_outbox_service.py)
построены на AsyncMock и проверяют вызовы ``session.execute``, а не поведение
SQL. Здесь проверяются реальные бизнес-инварианты outbox на настоящей БД:

* транзакционность enqueue (rollback бизнес-операции не оставляет писем);
* claim-изоляция (FOR UPDATE SKIP LOCKED — письмо не может быть захвачено
  двумя воркерами, т.е. не отправляется дважды);
* backoff/DLQ (transient → PENDING + next_attempt_at, permanent/exhausted → DLQ);
* watchdog requeue_stale_sending (зависшие SENDING возвращаются в очередь);
* админ-переходы (retry/cancel) по разрешённым статусам;
* cleanup (удаляются только старые SENT);
* полный цикл диспетчера process_email_outbox (реальные БД+Redis,
  monkeypatched SMTP).

Запуск: ./scripts/test-integration.sh tests/integration/test_email_outbox_lifecycle_db.py
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

_SMTP_CFG = {
    "host": "smtp.test.local",
    "port": 25,
    "from_address": "portal@test.local",
    "username": "",
    "password": "",
    "use_tls": False,
    "use_starttls": False,
}


def _now() -> datetime:
    return datetime.now(UTC)


async def _insert(
    session: AsyncSession,
    *,
    status: str = "PENDING",
    attempts: int = 0,
    max_attempts: int = 6,
    next_attempt_at: datetime | None = None,
    updated_at: datetime | None = None,
    kind: str = "generic",
    last_error: str | None = None,
) -> uuid.UUID:
    """Сырой INSERT с явными статусами/временами (RETURNING id).

    ORM-default'ы (updated_at=NOW()) намеренно не используются: тестам watchdog
    и claim нужны строки «из прошлого».
    """
    row = await session.execute(
        text(
            """
            INSERT INTO email_outbox (
                kind, to_email, subject, body_html, payload, status,
                attempts, max_attempts, next_attempt_at, updated_at, last_error
            ) VALUES (
                :kind, :to_email, 'Test subject', '<p>hi</p>',
                CAST('{}' AS JSONB), :status,
                :attempts, :max_attempts, :next_at, :updated_at, :last_error
            )
            RETURNING id
            """
        ),
        {
            "kind": kind,
            "to_email": f"rcpt-{uuid.uuid4().hex[:8]}@x.test",
            "status": status,
            "attempts": attempts,
            "max_attempts": max_attempts,
            # дефолт «минуту назад»: часы хоста и БД-контейнера могут расходиться
            # на миллисекунды — свежий _now() иногда опережает NOW() базы, и строка
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
                FROM email_outbox WHERE id = :id
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
    """INSERT реальным COMMIT'ом — видим другим соединениям (диспетчер)."""
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
                text("DELETE FROM email_outbox WHERE id = ANY(CAST(:ids AS UUID[]))"),
                {"ids": [str(i) for i in ids]},
            )
            await s.commit()


class TestOutboxTransactionInvariant:
    async def test_rollback_of_business_transaction_leaves_no_email(self, real_db_session):
        """Outbox-инвариант: enqueue в той же транзакции, что бизнес-операция.

        Если бизнес-операция откатывается ПОСЛЕ enqueue — письма быть не должно
        (иначе пользователи получают уведомления о несуществующих событиях).
        """
        from app.services.email_outbox import enqueue_outbox_email

        await enqueue_outbox_email(
            real_db_session,
            kind="generic",
            to_email="ghost@x.test",
            subject="Отменённая операция",
            body_html="<p>x</p>",
        )
        # caller-level rollback (например, исключение после enqueue)
        await real_db_session.rollback()

        left = (
            await real_db_session.execute(
                text("SELECT count(*) FROM email_outbox WHERE to_email = 'ghost@x.test'")
            )
        ).scalar_one()
        assert left == 0


class TestClaimPendingDb:
    async def test_claim_takes_only_ready_pending(self, real_db_session):
        from app.services.email_outbox import claim_pending

        ready = await _insert(real_db_session)
        future = await _insert(real_db_session, next_attempt_at=_now() + timedelta(hours=1))
        sent = await _insert(real_db_session, status="SENT")
        await real_db_session.flush()

        claimed = await claim_pending(real_db_session, limit=10)
        claimed_ids = {row["id"] for row in claimed}
        assert claimed_ids == {ready}
        # готовы к отправке — только не запланированное в будущее и не SENT
        assert (await _fetch(real_db_session, ready))["status"] == "SENDING"
        assert (await _fetch(real_db_session, future))["status"] == "PENDING"
        assert (await _fetch(real_db_session, sent))["status"] == "SENT"

    async def test_claim_respects_limit_in_fifo_order(self, real_db_session):
        from app.services.email_outbox import claim_pending

        base = _now() - timedelta(minutes=10)
        oldest = await _insert(real_db_session, next_attempt_at=base)
        middle = await _insert(real_db_session, next_attempt_at=base + timedelta(minutes=5))
        newest = await _insert(real_db_session, next_attempt_at=base + timedelta(minutes=9))
        await real_db_session.flush()

        claimed = await claim_pending(real_db_session, limit=2)
        assert [row["id"] for row in claimed] == [oldest, middle]
        assert (await _fetch(real_db_session, newest))["status"] == "PENDING"

    async def test_concurrent_claims_never_overlap(self, real_db_engine, outbox_cleanup):
        """FOR UPDATE SKIP LOCKED: два конкурентных воркера не заберут одно письмо.

        Это ядро гарантии «не отправлять дважды»: без SKIP LOCKED второй claim
        ждал бы блокировок (а при race — дублировал строки).
        """
        from app.services.email_outbox import claim_pending

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
            # транзакции обоих воркеров ещё открыты — проверки до commit/rollback.
            # Делёж может быть любым (3/3 при интерливинге, 0/6 при полной
            # сериализации на медленном раннере): SKIP LOCKED не обещает равное
            # деление, только непересечение и полноту захвата.
            assert not (ids_a & ids_b), "письмо захвачено двумя воркерами — двойная отправка"
            assert ids_a | ids_b == ids, "часть писем потеряна при конкурентном захвате"
            await worker_a.rollback()
            await worker_b.rollback()


class TestMarkSentFailedDb:
    async def test_mark_sent_sets_sent_at_and_clears_error(self, real_db_session):
        from app.services.email_outbox import claim_pending, mark_sent

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
        assert row["last_error_class"] is None

    async def test_mark_failed_transient_requeues_with_backoff(self, real_db_session):
        from app.services.email_outbox import mark_failed

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
        assert row["last_error"] == "connection refused"
        assert row["last_error_class"] == "transient"
        # defer = 30с + 15% джиттер для первой transient-попытки
        delta = (row["next_attempt_at"] - before).total_seconds()
        assert 25 <= delta <= 65, f"unexpected backoff {delta}s"

    async def test_mark_failed_permanent_goes_dlq_immediately(self, real_db_session):
        from app.services.email_outbox import mark_failed

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
        assert row["next_attempt_at"] == old_next  # не планируется повтор

    async def test_mark_failed_exhausted_attempts_goes_dlq(self, real_db_session):
        from app.services.email_outbox import mark_failed

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
        row = await _fetch(real_db_session, outbox_id)
        assert row["status"] == "DLQ"
        assert row["attempts"] == 6


class TestWatchdogDb:
    async def test_requeue_stale_sending_returns_only_old_rows(self, real_db_session):
        from app.services.email_outbox import requeue_stale_sending

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
        assert stale_row["next_attempt_at"] >= _now() - timedelta(seconds=5)
        assert (await _fetch(real_db_session, fresh))["status"] == "SENDING"


class TestAdminTransitionsDb:
    async def test_reschedule_for_retry_reset_and_keep_attempts(self, real_db_session):
        from app.services.email_outbox import reschedule_for_retry

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
        from app.services.email_outbox import reschedule_for_retry

        sending_id = await _insert(real_db_session, status="SENDING")
        await real_db_session.flush()

        ok = await reschedule_for_retry(real_db_session, sending_id)
        assert ok is False, "нельзя перезапустить письмо, которое сейчас отправляется"
        assert (await _fetch(real_db_session, sending_id))["status"] == "SENDING"

    @pytest.mark.parametrize(
        ("status", "expected"),
        [("PENDING", True), ("FAILED", True), ("DLQ", True), ("SENDING", False), ("SENT", False)],
    )
    async def test_cancel_state_machine(self, real_db_session, status: str, expected: bool):
        from app.services.email_outbox import cancel

        outbox_id = await _insert(real_db_session, status=status)
        await real_db_session.flush()

        assert await cancel(real_db_session, outbox_id) is expected
        final_status = (await _fetch(real_db_session, outbox_id))["status"]
        assert final_status == ("CANCELLED" if expected else status)


class TestCleanupDb:
    async def test_cleanup_deletes_only_old_sent(self, real_db_session):
        from app.services.email_outbox import cleanup_old_sent

        old_days = timedelta(days=40)
        old_sent = await _insert(real_db_session, status="SENT", updated_at=_now() - old_days)
        # cleanup смотрит на sent_at — проставим явно
        await real_db_session.execute(
            text("UPDATE email_outbox SET sent_at = :t WHERE id = :id"),
            {"t": _now() - old_days, "id": old_sent},
        )
        recent_sent = await _insert(real_db_session, status="SENT")
        await real_db_session.execute(
            text("UPDATE email_outbox SET sent_at = :t WHERE id = :id"),
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
            for r in (await real_db_session.execute(text("SELECT id FROM email_outbox"))).mappings()
        }
        assert remaining == {recent_sent, old_dlq, old_cancelled}


class TestDispatcherDb:
    """Полный цикл process_email_outbox: реальная PG + Redis, SMTP подменён.

    Диспетчер использует собственный AsyncSessionLocal (глобальный engine на
    DSN тест-стека) — строки для него обязаны быть закоммичены.
    """

    @staticmethod
    def _patch_smtp(monkeypatch, send_impl) -> list:
        import app.worker.tasks.email_outbox as worker_mod

        sent: list = []

        async def _fake_send(msg, cfg):
            sent.append(msg)
            if send_impl is not None:
                await send_impl(msg, cfg)

        monkeypatch.setattr(worker_mod, "smtp_send", _fake_send)
        monkeypatch.setattr(worker_mod, "load_smtp_config", lambda: dict(_SMTP_CFG))

        async def _no_helpdesk_cfg():
            return None

        monkeypatch.setattr(worker_mod, "load_helpdesk_smtp_config", _no_helpdesk_cfg)
        return sent

    async def test_dispatcher_sends_batch_and_recovers_stale_sending(
        self, real_db_engine, redis_client, outbox_cleanup, monkeypatch
    ):
        """Happy path + watchdog: PENDING уходит, зависший SENDING возвращается и уходит."""
        from app.worker.tasks.email_outbox import process_email_outbox

        sent = self._patch_smtp(monkeypatch, None)

        fresh = await _insert_committed(real_db_engine)
        stale_sending = await _insert_committed(
            real_db_engine,
            status="SENDING",
            updated_at=_now() - timedelta(seconds=700),
        )
        outbox_cleanup.extend([fresh, stale_sending])

        result = await process_email_outbox({"redis": redis_client})

        assert result == 2
        assert len(sent) == 2
        for outbox_id in (fresh, stale_sending):
            row = await _fetch_committed(real_db_engine, outbox_id)
            assert row["status"] == "SENT"
            assert row["sent_at"] is not None

    async def test_dispatcher_transient_failure_requeues_with_backoff(
        self, real_db_engine, redis_client, outbox_cleanup, monkeypatch
    ):
        from aiosmtplib.errors import SMTPResponseException

        from app.worker.tasks.email_outbox import process_email_outbox

        async def _raise_4xx(msg, cfg):
            raise SMTPResponseException(450, "greylisted")

        self._patch_smtp(monkeypatch, _raise_4xx)

        outbox_id = await _insert_committed(real_db_engine)
        outbox_cleanup.append(outbox_id)
        before = _now()

        result = await process_email_outbox({"redis": redis_client})

        assert result == 0
        row = await _fetch_committed(real_db_engine, outbox_id)
        assert row["status"] == "PENDING"
        assert row["attempts"] == 1
        assert row["last_error_class"] == "transient"
        delta = (row["next_attempt_at"] - before).total_seconds()
        assert 25 <= delta <= 65, f"unexpected backoff {delta}s"

    async def test_dispatcher_permanent_failure_goes_dlq(
        self, real_db_engine, redis_client, outbox_cleanup, monkeypatch
    ):
        from aiosmtplib.errors import SMTPResponseException

        from app.worker.tasks.email_outbox import process_email_outbox

        async def _raise_5xx(msg, cfg):
            raise SMTPResponseException(550, "no such user")

        self._patch_smtp(monkeypatch, _raise_5xx)

        outbox_id = await _insert_committed(real_db_engine)
        outbox_cleanup.append(outbox_id)

        result = await process_email_outbox({"redis": redis_client})

        assert result == 0
        row = await _fetch_committed(real_db_engine, outbox_id)
        assert row["status"] == "DLQ"
        assert row["attempts"] == 1
        assert row["last_error_class"] == "permanent"

    async def test_dispatcher_unconfigured_smtp_is_transient_not_dlq(
        self, real_db_engine, redis_client, outbox_cleanup, monkeypatch
    ):
        """Пустой SMTP-хост — проблема окружения: письмо ждёт настройки, не умирает в DLQ."""
        import app.worker.tasks.email_outbox as worker_mod
        from app.worker.tasks.email_outbox import process_email_outbox

        monkeypatch.setattr(worker_mod, "load_smtp_config", lambda: dict(_SMTP_CFG, host=""))

        async def _no_helpdesk_cfg():
            return None

        monkeypatch.setattr(worker_mod, "load_helpdesk_smtp_config", _no_helpdesk_cfg)
        monkeypatch.setattr(worker_mod, "smtp_send", self._fail_if_called())

        outbox_id = await _insert_committed(real_db_engine)
        outbox_cleanup.append(outbox_id)

        result = await process_email_outbox({"redis": redis_client})

        assert result == 0
        row = await _fetch_committed(real_db_engine, outbox_id)
        assert row["status"] == "PENDING"
        assert row["attempts"] == 1
        assert row["last_error_type"] == "ConfigurationError"
        assert row["last_error_class"] == "transient"

    @staticmethod
    def _fail_if_called():
        async def _must_not_send(msg, cfg):
            raise AssertionError("smtp_send не должен вызываться без настроенного SMTP")

        return _must_not_send
