"""ARQ-задачи для transactional messenger-outbox.

Зеркало :mod:`app.worker.tasks.email_outbox`:

* ``process_messenger_outbox`` — диспетчер очереди (каждые 15с):
    1. Watchdog ``requeue_stale_sending`` (возвращает зависшие SENDING в очередь).
    2. ``claim_pending`` (FOR UPDATE SKIP LOCKED, лимит DISPATCH_BATCH_SIZE).
    3. Для каждой записи: загрузить ``HelpdeskMaxBotSettings``, расшифровать
       токен, вызвать провайдер-клиент. Ошибка → ``mark_failed`` (через
       ``classify_http_error`` — transient/permanent), успех → ``mark_sent``.
* ``cleanup_messenger_outbox`` — раз в сутки чистит SENT старше 30 дней.

Distributed lock (по образцу helpdesk._acquire_lock) защищает от двойного
запуска при нескольких воркерах: 15с интервал + SKIP LOCKED уже дают
большую защиту, но MAX API может rate-limit'ить при параллельных вызовах,
поэтому lock строго обязателен.
"""

from __future__ import annotations

import secrets
from contextlib import suppress
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.secret_crypto import decrypt_secret
from app.models.helpdesk import HelpdeskMaxBotSettings
from app.services.max_messenger import (
    MaxApiError,
    classify_http_error,
    send_message,
)
from app.services.messenger_outbox import (
    PROVIDER_MAX,
    claim_pending,
    cleanup_old_sent,
    mark_failed,
    mark_sent,
    requeue_stale_sending,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

DISPATCH_BATCH_SIZE = 20
STALE_SENDING_TIMEOUT_SECONDS = 600

# Distributed lock (по образцу helpdesk.DIGEST_LOCK_KEY).
MESSENGER_OUTBOX_LOCK_KEY = "messenger:outbox:dispatch:lock"
# 2 минуты: batch быстрая, но MAX API таймаут 10с × 20 записей = ~200с в худшем случае.
MESSENGER_OUTBOX_LOCK_TTL = 120

_LOCK_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) "
    "else return 0 end"
)


async def _acquire_lock(redis: Redis, key: str, ttl: int) -> str | None:
    """Тот же паттерн, что в ``app.worker.tasks.helpdesk._acquire_lock``."""
    token = secrets.token_hex(16)
    acquired = await redis.set(key, token, nx=True, ex=ttl)
    if not acquired:
        return None
    return token


async def _release_lock(redis: Redis, key: str, token: str) -> None:
    with suppress(Exception):
        # ``redis.asyncio.Redis.eval`` асинхронен, но в stub'е redis-py имеет
        # перегрузку, возвращающую ``Awaitable[str] | str`` → mypy-error на
        # ``await``. Локальное игнорирование чистее, чем ``cast("Any", ...)``
        # на каждом вызове (см. ``tasks/helpdesk.py:_release_lock``).
        await redis.eval(  # type: ignore[misc]
            _LOCK_RELEASE_LUA, 1, key, token
        )


async def _load_max_settings(db: AsyncSession) -> HelpdeskMaxBotSettings | None:
    return (
        (
            await db.execute(
                select(HelpdeskMaxBotSettings).where(HelpdeskMaxBotSettings.id == 1)
            )
        )
        .scalars()
        .one_or_none()
    )


async def _dispatch_for_provider(
    *,
    provider: str,
    row: dict,
    bot_token_decrypted: str,
    chat_id_from_settings: str,
) -> None:
    """Вызвать провайдер-клиент для одной outbox-записи.

    ``chat_id`` в строкке outbox имеет приоритет (он фиксируется в момент
    создания заявки и принадлежит конкретному чату), но если он пустой —
    берётся из текущих настроек (для обратной совместимости при ручном
    редактировании). ``payload`` хранит attachments/format.
    """
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        # asyncpg/SQLAlchemy возвращает JSONB как dict, но на всякий случай.
        import json

        payload = json.loads(payload) if payload else {}

    chat_id = row.get("chat_id") or chat_id_from_settings
    attachments = payload.get("attachments") or []
    # JSON-значение из payload приходит как ``Any``; коалесцируем и
    # ограничиваем двумя форматами, поддерживаемыми MAX (markdown/html).
    # ``plain`` MAX НЕ поддерживает — парсер падает с "Can't deserialize body".
    raw_format = payload.get("format") or "markdown"
    format_map: dict[str, Literal["markdown", "html"]] = {
        "markdown": "markdown",
        "html": "html",
    }
    format_ = format_map.get(raw_format, "markdown") if isinstance(raw_format, str) else "markdown"

    if provider == PROVIDER_MAX:
        await send_message(
            bot_token=bot_token_decrypted,
            chat_id=chat_id,
            text=row["text"],
            attachments=attachments,
            format_=format_,
        )
        return

    # Неизвестный провайдер — permanent fail (не ретраим).
    raise MaxApiError(f"Unknown messenger provider: {provider!r}", status_code=None)


async def process_messenger_outbox(ctx: dict) -> int:
    """Обрабатывает пачку PENDING messenger-сообщений. Возвращает кол-во отправленных.

    Защита от двойного запуска: distributed lock (SKIP LOCKED в claim —
    дополнительная защита, но lock обязателен из-за rate-limits MAX).
    """
    redis = ctx.get("redis")
    if redis is None:
        logger.warning("messenger_outbox.no_redis_in_context")
        return 0

    lock_token = await _acquire_lock(redis, MESSENGER_OUTBOX_LOCK_KEY, MESSENGER_OUTBOX_LOCK_TTL)
    if lock_token is None:
        return 0

    sent_ok = 0
    try:
        async with AsyncSessionLocal() as session, session.begin():
            await requeue_stale_sending(
                session, older_than_seconds=STALE_SENDING_TIMEOUT_SECONDS
            )
            claimed = await claim_pending(session, limit=DISPATCH_BATCH_SIZE)
        if not claimed:
            return 0

        # Загружаем MAX-настройки один раз на батч (токен + chat_id fallback).
        async with AsyncSessionLocal() as db:
            max_settings = await _load_max_settings(db)

        if max_settings is None or not max_settings.enabled:
            # MAX-канал выключен между созданием заявки и обработкой →
            # возвращаем всё в PENDING (transient — фичу могут включить,
            # или админ удалил настройки по ошибке и восстановит).
            async with AsyncSessionLocal() as session, session.begin():
                for row in claimed:
                    await mark_failed(
                        session,
                        row["id"],
                        error="MAX bot settings disabled or missing",
                        error_type="ConfigurationError",
                        error_class="transient",
                        current_attempts=row["attempts"],
                        max_attempts=row["max_attempts"],
                    )
            logger.warning(
                "messenger_outbox.dispatch.max_disabled", claimed=len(claimed)
            )
            return 0

        if not max_settings.bot_token_enc or not max_settings.chat_id:
            # enabled=True, но токен/chat_id потеряны (edge-кейс при ручном
            # редактировании БД). Permanent — конфиг сломан, нечего ретраить.
            async with AsyncSessionLocal() as session, session.begin():
                for row in claimed:
                    await mark_failed(
                        session,
                        row["id"],
                        error="MAX bot token or chat_id missing while enabled",
                        error_type="ConfigurationError",
                        error_class="permanent",
                        current_attempts=row["attempts"],
                        max_attempts=row["max_attempts"],
                    )
            logger.error(
                "messenger_outbox.dispatch.max_misconfigured", claimed=len(claimed)
            )
            return 0

        try:
            bot_token = decrypt_secret(max_settings.bot_token_enc)
        except Exception as exc:
            # Токен не расшифровывается (изменился SECRET_KEY?). Permanent —
            # ретраи не помогут, нужен фикс окружения.
            logger.exception("messenger_outbox.token_decrypt_failed", error=str(exc))
            async with AsyncSessionLocal() as session, session.begin():
                for row in claimed:
                    await mark_failed(
                        session,
                        row["id"],
                        error="Failed to decrypt bot token",
                        error_type=type(exc).__name__,
                        error_class="permanent",
                        current_attempts=row["attempts"],
                        max_attempts=row["max_attempts"],
                    )
            return 0

        for row in claimed:
            try:
                await _dispatch_for_provider(
                    provider=row["provider"],
                    row=row,
                    bot_token_decrypted=bot_token,
                    chat_id_from_settings=max_settings.chat_id or "",
                )
            except Exception as exc:
                error_class = classify_http_error(exc)
                error_type = type(exc).__name__
                logger.exception(
                    "messenger_outbox.send_failed",
                    outbox_id=str(row["id"]),
                    provider=row["provider"],
                    chat_id=row["chat_id"],
                    error=str(exc),
                    error_type=error_type,
                    error_class=error_class,
                    attempts=row["attempts"],
                )
                async with AsyncSessionLocal() as session, session.begin():
                    await mark_failed(
                        session,
                        row["id"],
                        error=str(exc),
                        error_type=error_type,
                        error_class=error_class,
                        current_attempts=row["attempts"],
                        max_attempts=row["max_attempts"],
                    )
                continue

            async with AsyncSessionLocal() as session, session.begin():
                await mark_sent(session, row["id"])
            sent_ok += 1
            logger.info(
                "messenger_outbox.sent",
                outbox_id=str(row["id"]),
                provider=row["provider"],
                chat_id=row["chat_id"],
            )
    except Exception as exc:
        logger.exception("messenger_outbox.dispatch_failed", error=str(exc))
    finally:
        await _release_lock(redis, MESSENGER_OUTBOX_LOCK_KEY, lock_token)
    return sent_ok


async def cleanup_messenger_outbox(ctx: dict) -> int:
    """Раз в сутки чистит SENT-записи старше 30 дней (зеркало cleanup_email_outbox)."""
    try:
        async with AsyncSessionLocal() as session, session.begin():
            return await cleanup_old_sent(session, older_than_days=30)
    except Exception as exc:
        logger.exception("messenger_outbox.cleanup_failed", error=str(exc))
        return 0
