"""Unit-тесты distributed locks для helpdesk cron (H-1).

До правки archive-семейство (``archive_closed_tickets_task`` /
``create_next_helpdesk_archive_partition`` / ``cleanup_helpdesk_attachments_task``)
не брало Redis-lock — при двух воркерах ``archive_closed_tickets`` дублировал
работу (SELECT без ``FOR UPDATE SKIP LOCKED``, оба выбирали одни и те же
``closed``-тикеты до commit). Теперь общий хелпер ``_acquire_lock`` /
``_release_lock`` оборачивает все cron, включая poll/digest.

Тестируются чистые функции взятия/освобождения лока (Redis — FakeAsyncRedis) и
поведение воркеров при занятом локе (no-op без работы).

PII-маска ``_email_domain`` (H-11) — здесь же, отдельный класс.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.helpdesk.ingress import _email_domain
from app.worker.tasks.helpdesk import (
    ARCHIVE_LOCK_KEY,
    CLEANUP_LOCK_KEY,
    DIGEST_LOCK_KEY,
    DRAFT_CLEANUP_LOCK_KEY,
    PARTITION_LOCK_KEY,
    POLL_LOCK_KEY,
    _acquire_lock,
    _release_lock,
)


def _fake_redis(set_returns: object = True, eval_returns: int = 1) -> MagicMock:
    """Redis-заглушка: ``set(nx=True)`` возвращает ``set_returns``, ``eval``
    возвращает ``eval_returns`` (как Lua-скрипт release: 1 = удалён, 0 = не владелец).

    Оба метода — ``AsyncMock``, чтобы ``await redis.set(...)`` работал."""
    redis = MagicMock()
    redis.set = AsyncMock(return_value=set_returns)
    redis.eval = AsyncMock(return_value=eval_returns)
    return redis


@pytest.mark.asyncio
class TestAcquireLock:
    async def test_acquires_when_free(self) -> None:
        """``SET NX EX`` вернул ``True`` → возвращаем ``lock_token``."""
        redis = _fake_redis(set_returns=True)
        token = await _acquire_lock(redis, "test:lock", ttl=60)
        assert token is not None
        assert isinstance(token, str) and len(token) > 0
        # ``SET NX EX`` с правильным ключом/TTL.
        redis.set.assert_awaited_once()
        args, kwargs = redis.set.call_args
        assert args[0] == "test:lock"
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == 60

    async def test_returns_none_when_held(self) -> None:
        """``SET NX`` вернул ``None`` (лок уже занят другим воркером) → возвращаем
        ``None``, работа cron пропускается."""
        redis = _fake_redis(set_returns=None)
        token = await _acquire_lock(redis, "test:lock", ttl=60)
        assert token is None

    async def test_returns_none_when_false(self) -> None:
        """Защита: ``False`` (если конкретный клиент так возвращает отказ)."""
        redis = _fake_redis(set_returns=False)
        token = await _acquire_lock(redis, "test:lock", ttl=60)
        assert token is None

    async def test_token_changes_between_calls(self) -> None:
        """Каждый acquire генерирует уникальный ``token`` (нужен для атомарной
        проверки владения в release — иначе воркер A удалит лок воркера B)."""
        redis = _fake_redis(set_returns=True)
        t1 = await _acquire_lock(redis, "k", 1)
        t2 = await _acquire_lock(redis, "k", 1)
        assert t1 != t2


@pytest.mark.asyncio
class TestReleaseLock:
    async def test_releases_with_correct_token(self) -> None:
        """Release вызывает Lua-eval с ключом и токеном владения."""
        redis = _fake_redis()
        await _release_lock(redis, "test:lock", "my-token")
        redis.eval.assert_awaited_once()
        args = redis.eval.call_args.args
        # (script, numkeys, key, token) — Lua signature release.
        assert args[0].startswith("if redis.call('get'")  # _LOCK_RELEASE_LUA
        assert args[2] == "test:lock"
        assert args[3] == "my-token"

    async def test_swallows_eval_exception(self) -> None:
        """Release в ``finally``: исключение (сеть/таймаут Redis) НЕ должно ронять
        воркер — лок истечёт по TTL сам."""
        redis = MagicMock()
        redis.eval = AsyncMock(side_effect=RuntimeError("redis down"))
        # Не поднимает исключение.
        await _release_lock(redis, "k", "t")


@pytest.mark.asyncio
class TestArchiveFamilyAcquiresLock:
    """Archive/partition/cleanup cron должны брать distributed lock перед работой.
    Без лока (старое поведение) — гонка между воркерами."""

    async def test_archive_returns_zero_when_lock_held(self) -> None:
        """Если лок ``helpdesk:archive:lock`` занят — задача завершается без работы
        (skip, не дублирует archivацию другого воркера)."""
        from app.worker.tasks import helpdesk as h

        redis = _fake_redis(set_returns=None)  # лок занят
        ctx = {"redis": redis}

        with (
            patch.object(h, "_module_enabled", new=AsyncMock(return_value=True)),
            patch.object(h, "archive_closed_tickets", new=AsyncMock(return_value=999)) as work,
        ):
            result = await h.archive_closed_tickets_task(ctx)
        assert result == 0
        # Работа не выполнена — сервис не вызывался (лок предотвращает дубль).
        work.assert_not_awaited()

    async def test_partition_returns_empty_when_lock_held(self) -> None:
        from app.worker.tasks import helpdesk as h

        redis = _fake_redis(set_returns=None)
        ctx = {"redis": redis}

        with (
            patch.object(h, "_module_enabled", new=AsyncMock(return_value=True)),
            patch("app.worker.tasks.helpdesk.asyncpg.connect", new=AsyncMock()),
            patch.object(h, "ensure_helpdesk_archive_partitions", new=AsyncMock()) as work,
        ):
            result = await h.create_next_helpdesk_archive_partition(ctx)
        assert result == ""
        work.assert_not_awaited()

    async def test_cleanup_returns_zero_when_lock_held(self) -> None:
        from app.worker.tasks import helpdesk as h

        redis = _fake_redis(set_returns=None)
        ctx = {"redis": redis}

        with (
            patch.object(h, "_module_enabled", new=AsyncMock(return_value=True)),
            patch.object(h, "cleanup_archived_files", new=AsyncMock(return_value=999)) as work,
        ):
            result = await h.cleanup_helpdesk_attachments_task(ctx)
        assert result == 0
        work.assert_not_awaited()

    async def test_draft_cleanup_returns_zero_when_lock_held(self) -> None:
        """Draft-cleanup берёт ``DRAFT_CLEANUP_LOCK_KEY``: при занятом локе —
        no-op, не дублирует очистку другого воркера (симметрично archive/cleanup)."""
        from app.worker.tasks import helpdesk as h

        redis = _fake_redis(set_returns=None)  # lock held
        ctx = {"redis": redis}

        with (
            patch.object(h, "_module_enabled", new=AsyncMock(return_value=True)),
            patch.object(h, "cleanup_expired_drafts", new=AsyncMock(return_value=999)) as work,
        ):
            result = await h.cleanup_expired_drafts_task(ctx)
        assert result == 0
        work.assert_not_awaited()

    async def test_draft_cleanup_proceeds_when_lock_acquired(self) -> None:
        """Лок свободен → задача вызывает ``cleanup_expired_drafts`` и коммитит."""
        from app.worker.tasks import helpdesk as h

        redis = _fake_redis(set_returns=True)
        ctx = {"redis": redis}

        fake_db = AsyncMock()
        fake_db.commit = AsyncMock()
        with (
            patch.object(h, "_module_enabled", new=AsyncMock(return_value=True)),
            patch.object(h, "AsyncSessionLocal") as session_cls,
            patch.object(h, "cleanup_expired_drafts", new=AsyncMock(return_value=5)),
        ):
            session_cls.return_value.__aenter__.return_value = fake_db
            session_cls.return_value.__aexit__.return_value = None
            result = await h.cleanup_expired_drafts_task(ctx)
        assert result == 5
        # ``SET NX EX`` на правильном ключе.
        assert redis.set.call_args.args[0] == DRAFT_CLEANUP_LOCK_KEY
        # Removed>0 → commit вызван (орphan-удаление фиксируется).
        fake_db.commit.assert_awaited_once()

    async def test_draft_cleanup_skips_commit_when_nothing_removed(self) -> None:
        """Нечего чистить (removed=0) → commit не вызывается лишний раз."""
        from app.worker.tasks import helpdesk as h

        redis = _fake_redis(set_returns=True)
        ctx = {"redis": redis}

        fake_db = AsyncMock()
        fake_db.commit = AsyncMock()
        with (
            patch.object(h, "_module_enabled", new=AsyncMock(return_value=True)),
            patch.object(h, "AsyncSessionLocal") as session_cls,
            patch.object(h, "cleanup_expired_drafts", new=AsyncMock(return_value=0)),
        ):
            session_cls.return_value.__aenter__.return_value = fake_db
            session_cls.return_value.__aexit__.return_value = None
            result = await h.cleanup_expired_drafts_task(ctx)
        assert result == 0
        fake_db.commit.assert_not_awaited()

    async def test_draft_cleanup_skips_when_module_disabled(self) -> None:
        """Модуль helpdesk выключен → no-op без работы (как все helpdesk cron)."""
        from app.worker.tasks import helpdesk as h

        redis = _fake_redis(set_returns=True)
        ctx = {"redis": redis}

        with (
            patch.object(h, "_module_enabled", new=AsyncMock(return_value=False)),
            patch.object(h, "cleanup_expired_drafts", new=AsyncMock()) as work,
        ):
            result = await h.cleanup_expired_drafts_task(ctx)
        assert result == 0
        work.assert_not_awaited()

    async def test_archive_proceeds_when_lock_acquired(self) -> None:
        """Лок свободен → задача берёт его и вызывает сервис."""
        from app.worker.tasks import helpdesk as h

        redis = _fake_redis(set_returns=True)
        ctx = {"redis": redis}

        with (
            patch.object(h, "_module_enabled", new=AsyncMock(return_value=True)),
            patch.object(h, "archive_closed_tickets", new=AsyncMock(return_value=3)),
        ):
            result = await h.archive_closed_tickets_task(ctx)
        assert result == 3
        # ``SET NX EX`` на правильном ключе.
        assert redis.set.call_args.args[0] == ARCHIVE_LOCK_KEY


class TestLockKeys:
    """Все lock-keys зарезервированы (защита от случайного rename/refactor)."""

    def test_keys_are_distinct(self) -> None:
        keys = {
            POLL_LOCK_KEY,
            ARCHIVE_LOCK_KEY,
            PARTITION_LOCK_KEY,
            CLEANUP_LOCK_KEY,
            DIGEST_LOCK_KEY,
            DRAFT_CLEANUP_LOCK_KEY,
        }
        assert len(keys) == 6

    def test_all_prefixed(self) -> None:
        """Все lock-keys под ``helpdesk:*`` namespace (для grep/мониторинга)."""
        for k in (
            POLL_LOCK_KEY,
            ARCHIVE_LOCK_KEY,
            PARTITION_LOCK_KEY,
            CLEANUP_LOCK_KEY,
            DIGEST_LOCK_KEY,
            DRAFT_CLEANUP_LOCK_KEY,
        ):
            assert k.startswith("helpdesk:"), f"{k} вне helpdesk-namespace"


class TestEmailDomainMasking:
    """H-11: ``_email_domain`` маскирует email для логов (``u***@domain``).
    Полный адрес — PII, в info-лог ``token_sender_mismatch`` попадают только
    домен + первый символ local-part (диагностика расхождения sender/requester
    без утечки адресов в access-логи/Sentry)."""

    def test_masks_local_part(self) -> None:
        assert _email_domain("alice@company.local") == "a***@company.local"

    def test_keeps_domain(self) -> None:
        """Домен оставляем — нужен для диагностики («письмо снаружи организации»)."""
        assert _email_domain("user@example.com").endswith("@example.com")

    def test_single_char_local(self) -> None:
        """Граничный случай: local-part длиной 1 символ (``x@x.test``)."""
        assert _email_domain("x@x.test") == "x***@x.test"

    def test_no_at_returns_invalid_marker(self) -> None:
        """Невалидный email — маркер ``(invalid)`` (не ``None``, чтобы лог-строка
        оставалась читаемой в grafana/loki)."""
        assert _email_domain("not-an-email") == "(invalid)"

    def test_empty_local_returns_empty_marker(self) -> None:
        """Защита от ``@domain`` (нет local-part)."""
        result = _email_domain("@company.local")
        assert "company.local" in result
        assert "***" not in result  # пустой local — не маскируем

    def test_empty_domain_handled(self) -> None:
        result = _email_domain("user@")
        assert "user" not in result or "***" in result  # local-часть скрыта
        assert "(empty)" in result
