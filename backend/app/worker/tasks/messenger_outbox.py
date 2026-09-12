"""ARQ-задачи для transactional messenger-outbox.

Зеркало :mod:`app.worker.tasks.email_outbox`:

* ``process_messenger_outbox`` — диспетчер очереди (каждые 15с):
    1. Watchdog ``requeue_stale_sending`` (возвращает зависшие SENDING в очередь).
    2. ``claim_pending`` (FOR UPDATE SKIP LOCKED, лимит DISPATCH_BATCH_SIZE).
    3. Группировка по ``provider``: каждая группа обрабатывается своими
       настройками и клиентом (``_dispatch_max`` / ``_dispatch_matrix``).
       Ошибка → ``mark_failed`` (через classify провайдера — transient/
       permanent), успех → ``mark_sent``.
* ``cleanup_messenger_outbox`` — раз в сутки чистит SENT старше 30 дней.

Distributed lock (по образцу helpdesk._acquire_lock) защищает от двойного
запуска при нескольких воркерах: 15с интервал + SKIP LOCKED уже дают
большую защиту, но внешние API могут rate-limit'ить при параллельных вызовах,
поэтому lock строго обязателен. Lock же исключает гонки на account data
``m.direct`` Matrix-бота (read-modify-write в ``_dispatch_matrix``).
"""

from __future__ import annotations

import secrets
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.secret_crypto import decrypt_secret
from app.models.helpdesk import HelpdeskMaxBotSettings
from app.models.matrix_bot import MatrixBotSettings
from app.services.matrix_messenger import (
    DmResolver,
)
from app.services.matrix_messenger import (
    classify_http_error as classify_matrix_error,
)
from app.services.matrix_messenger import (
    send_message as matrix_send_message,
)
from app.services.max_messenger import (
    classify_http_error as classify_max_error,
)
from app.services.max_messenger import (
    send_message as max_send_message,
)
from app.services.messenger_outbox import (
    PROVIDER_MATRIX,
    PROVIDER_MAX,
    claim_pending,
    cleanup_old_sent,
    mark_failed,
    mark_sent,
    requeue_stale_sending,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from redis.asyncio import Redis

logger = get_logger(__name__)

DISPATCH_BATCH_SIZE = 20
STALE_SENDING_TIMEOUT_SECONDS = 600
# Ретеншн SENT-записей: 7 дней (решение 2026-08-17, хардкод; DLQ не трогаем).
SENT_RETENTION_DAYS = 7

# Distributed lock (по образцу helpdesk.DIGEST_LOCK_KEY).
MESSENGER_OUTBOX_LOCK_KEY = "messenger:outbox:dispatch:lock"
# 2 минуты: batch быстрая, но внешние API-таймауты 10с × 20 записей = ~200с
# в худшем случае.
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
        await redis.eval(_LOCK_RELEASE_LUA, 1, key, token)  # type: ignore[misc]  # redis-py async-overload typing


def _row_payload(row: dict) -> dict:
    """``payload`` outbox-строки (JSONB → dict; на всякий случай — str → parse)."""
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        import json

        return json.loads(payload) if payload else {}
    return payload if isinstance(payload, dict) else {}


async def _fail_rows(
    rows: list[dict],
    *,
    error: str,
    error_type: str,
    error_class: str,
) -> None:
    """Пометить группу записей failed (общий сбой настроек провайдера)."""
    async with AsyncSessionLocal() as session, session.begin():
        for row in rows:
            await mark_failed(
                session,
                row["id"],
                error=error,
                error_type=error_type,
                error_class=error_class,
                current_attempts=row["attempts"],
                max_attempts=row["max_attempts"],
            )


async def _send_rows(
    rows: list[dict],
    *,
    sender: Callable[[dict], Awaitable[None]],
    classify: Callable[[BaseException], str],
) -> int:
    """Общий цикл отправки: sender(row) → mark_sent / mark_failed(classify)."""
    sent_ok = 0
    for row in rows:
        try:
            await sender(row)
        except Exception as exc:
            error_class = classify(exc)
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
    return sent_ok


async def _load_max_settings(db: AsyncSession) -> HelpdeskMaxBotSettings | None:
    return (
        (await db.execute(select(HelpdeskMaxBotSettings).where(HelpdeskMaxBotSettings.id == 1)))
        .scalars()
        .one_or_none()
    )


async def _load_matrix_settings(db: AsyncSession) -> MatrixBotSettings | None:
    return (
        (await db.execute(select(MatrixBotSettings).where(MatrixBotSettings.id == 1)))
        .scalars()
        .one_or_none()
    )


# ── MAX (общий чат поддержки) ────────────────────────────────────────────


async def _dispatch_max(rows: list[dict]) -> int:
    """Отправка MAX-строк: токен + chat_id из helpdesk_max_bot_settings."""
    async with AsyncSessionLocal() as db:
        settings = await _load_max_settings(db)

    if settings is None or not settings.enabled:
        # Канал выключен между созданием заявки и обработкой → возвращаем всё
        # в PENDING (transient — фичу могут включить, или админ удалил
        # настройки по ошибке и восстановит).
        await _fail_rows(
            rows,
            error="MAX bot settings disabled or missing",
            error_type="ConfigurationError",
            error_class="transient",
        )
        logger.warning("messenger_outbox.dispatch.max_disabled", claimed=len(rows))
        return 0

    if not settings.bot_token_enc or not settings.chat_id:
        # enabled=True, но токен/chat_id потеряны (edge-кейс при ручном
        # редактировании БД). Permanent — конфиг сломан, нечего ретраить.
        await _fail_rows(
            rows,
            error="MAX bot token or chat_id missing while enabled",
            error_type="ConfigurationError",
            error_class="permanent",
        )
        logger.error("messenger_outbox.dispatch.max_misconfigured", claimed=len(rows))
        return 0

    try:
        bot_token = decrypt_secret(settings.bot_token_enc)
    except Exception as exc:
        # Токен не расшифровывается (изменился SECRET_KEY?). Permanent —
        # ретраи не помогут, нужен фикс окружения.
        logger.exception("messenger_outbox.token_decrypt_failed", error=str(exc))
        await _fail_rows(
            rows,
            error="Failed to decrypt bot token",
            error_type=type(exc).__name__,
            error_class="permanent",
        )
        return 0

    async def _send_max(row: dict) -> None:
        """``chat_id`` в строке outbox имеет приоритет (фиксируется в момент
        создания заявки), но если он пустой — берётся из текущих настроек
        (обратная совместимость при ручном редактировании)."""
        payload = _row_payload(row)
        chat_id = row.get("chat_id") or settings.chat_id or ""
        attachments = payload.get("attachments") or []
        # Коалесцируем формат к markdown/html (``plain`` MAX не принимает).
        raw_format = payload.get("format") or "markdown"
        format_map: dict[str, Literal["markdown", "html"]] = {
            "markdown": "markdown",
            "html": "html",
        }
        format_ = (
            format_map.get(raw_format, "markdown") if isinstance(raw_format, str) else "markdown"
        )
        await max_send_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=row["text"],
            attachments=attachments,
            format_=format_,
        )

    return await _send_rows(rows, sender=_send_max, classify=classify_max_error)


# ── Matrix (персональные DM) ─────────────────────────────────────────────


async def _dispatch_matrix(rows: list[dict]) -> int:
    """Отправка matrix-строк: персональные DM по MXID из ``chat_id``.

    ``chat_id`` matrix-строк хранит MXID получателя (``@user:server``) —
    админ в логах видит человека; комната резолвится при отправке.
    ``txn_id`` = UUID outbox-строки: идемпотентность на стороне Synapse,
    ретрай не задублирует сообщение.
    """
    async with AsyncSessionLocal() as db:
        settings = await _load_matrix_settings(db)

    if settings is None or not settings.enabled:
        await _fail_rows(
            rows,
            error="Matrix bot settings disabled or missing",
            error_type="ConfigurationError",
            error_class="transient",
        )
        logger.warning("messenger_outbox.dispatch.matrix_disabled", claimed=len(rows))
        return 0

    if not (settings.access_token_enc and settings.homeserver_url and settings.bot_user_id):
        # enabled=True, но конфигурация потеряна (edge-кейс ручного
        # редактирования БД). Permanent — нечего ретраить.
        await _fail_rows(
            rows,
            error="Matrix bot access_token/homeserver_url/bot_user_id missing while enabled",
            error_type="ConfigurationError",
            error_class="permanent",
        )
        logger.error("messenger_outbox.dispatch.matrix_misconfigured", claimed=len(rows))
        return 0

    try:
        access_token = decrypt_secret(settings.access_token_enc)
    except Exception as exc:
        logger.exception("messenger_outbox.matrix_token_decrypt_failed", error=str(exc))
        await _fail_rows(
            rows,
            error="Failed to decrypt Matrix access token",
            error_type=type(exc).__name__,
            error_class="permanent",
        )
        return 0

    # Локальные не-None биндинги после валидации выше (mypy не сужает атрибуты).
    homeserver_url = settings.homeserver_url
    bot_user_id = settings.bot_user_id
    assert homeserver_url is not None and bot_user_id is not None

    resolver = DmResolver(
        homeserver_url=homeserver_url,
        access_token=access_token,
        bot_user_id=bot_user_id,
    )

    async def _send_matrix(row: dict) -> None:
        payload: dict[str, Any] = _row_payload(row)
        formatted_body = payload.get("formatted_body")
        room_id = await resolver.resolve(row["chat_id"])
        await matrix_send_message(
            homeserver_url=homeserver_url,
            access_token=access_token,
            room_id=room_id,
            txn_id=str(row["id"]),
            body=row["text"],
            formatted_body=formatted_body if isinstance(formatted_body, str) else None,
        )

    return await _send_rows(rows, sender=_send_matrix, classify=classify_matrix_error)


async def process_messenger_outbox(ctx: dict) -> int:
    """Обрабатывает пачку PENDING messenger-сообщений. Возвращает кол-во отправленных.

    Защита от двойного запуска: distributed lock (SKIP LOCKED в claim —
    дополнительная защита, но lock обязателен из-за rate-limits внешних API).
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
            await requeue_stale_sending(session, older_than_seconds=STALE_SENDING_TIMEOUT_SECONDS)
            claimed = await claim_pending(session, limit=DISPATCH_BATCH_SIZE)
        if not claimed:
            return 0

        # Группировка по провайдеру: у каждого свои настройки и клиент.
        groups: dict[str, list[dict]] = {}
        for row in claimed:
            groups.setdefault(row["provider"], []).append(row)

        for provider, rows in groups.items():
            if provider == PROVIDER_MAX:
                sent_ok += await _dispatch_max(rows)
            elif provider == PROVIDER_MATRIX:
                sent_ok += await _dispatch_matrix(rows)
            else:
                # Неизвестный провайдер — permanent fail (не ретраим).
                logger.error(
                    "messenger_outbox.unknown_provider",
                    provider=provider,
                    claimed=len(rows),
                )
                await _fail_rows(
                    rows,
                    error=f"Unknown messenger provider: {provider!r}",
                    error_type="ConfigurationError",
                    error_class="permanent",
                )
    except Exception as exc:
        logger.exception("messenger_outbox.dispatch_failed", error=str(exc))
    finally:
        await _release_lock(redis, MESSENGER_OUTBOX_LOCK_KEY, lock_token)
    return sent_ok


async def cleanup_messenger_outbox(ctx: dict) -> int:
    """Раз в сутки чистит SENT-записи старше SENT_RETENTION_DAYS (зеркало
    cleanup_email_outbox; 7 дней — решение 2026-08-17, хардкод)."""
    try:
        async with AsyncSessionLocal() as session, session.begin():
            return await cleanup_old_sent(session, older_than_days=SENT_RETENTION_DAYS)
    except Exception as exc:
        logger.exception("messenger_outbox.cleanup_failed", error=str(exc))
        return 0
