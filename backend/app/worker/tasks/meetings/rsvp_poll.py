"""ARQ-задача поллинга RSVP-ответов из общего ящика портала.

Клон каркаса ``poll_helpdesk_mailbox`` / ``run_erp_sync``: cron каждые 30 с →
interval-guard (реальный интервал 60 с) → distributed lock → работа.

Цикл: fetch валидных IMIP-REPLY → одна транзакция на батч (upsert статусов +
лог Message-ID + in-app уведомления создателю) → commit → публикация
уведомлений в Redis Stream + SSE ``meeting_changed`` → удаление обработанных
писем из ящика. Письма без календарного REPLY не трогаются (общий ящик).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.services.email_settings import imap_configured, load_email_settings
from app.services.meetings.realtime import publish_meeting_event
from app.services.meetings.rsvp_ingest import (
    RSVP_LAST_POLL_KEY,
    RSVP_POLL_INTERVAL_SECONDS,
    RSVP_POLL_LOCK_KEY,
    RSVP_POLL_LOCK_TTL,
    STATUS_VERBS_RU,
    ReplyCandidate,
    apply_reply,
    delete_reply_messages,
    fetch_reply_candidates,
)
from app.services.notifications import create_notification

logger = get_logger(__name__)

_LOCK_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) "
    "else return 0 end"
)


async def _acquire_lock(redis: Redis, key: str, ttl: int) -> str | None:
    import secrets

    token = secrets.token_hex(16)
    acquired = await redis.set(key, token, nx=True, ex=ttl)
    return token if acquired else None


async def _release_lock(redis: Redis, key: str, token: str) -> None:
    from contextlib import suppress

    with suppress(Exception):
        await redis.eval(_LOCK_RELEASE_LUA, 1, key, token)  # type: ignore[misc]  # redis-py async-overload typing


def _gates_open() -> str | None:
    """Причина skip или None, если фичи разрешено работать."""
    from app.core.modules_config import load_modules

    meetings = load_modules().meetings
    if not meetings.enabled:
        return "module_disabled"
    if not meetings.rsvp_ingest_enabled:
        return "rsvp_ingest_disabled"
    return None


async def _ingest_batch(
    db: AsyncSession, redis: Redis, candidates: list[ReplyCandidate]
) -> tuple[dict[str, int], list[str], list[Any], list[tuple[Any, ...]]]:
    """Применить ответы в транзакции; вернуть (счётчики, IMAP-UID'ы к удалению,
    publish-коллбеки уведомлений, SSE-события).

    Уведомления создателю — одно на письмо (не на экземпляр серии): create_notification
    пишет в ту же транзакцию, publish-коллбеки возвращаются и вызываются после commit.
    """
    counters = {"applied": 0, "duplicate": 0, "not_found": 0, "not_invited": 0, "ignored": 0}
    processed_uids: list[str] = []
    publish_callbacks: list[Any] = []
    sse_events: list[tuple[Any, ...]] = []

    for candidate in candidates:
        outcome = await apply_reply(db, candidate.parsed, candidate.message_id)
        counters[outcome.status] = counters.get(outcome.status, 0) + 1
        processed_uids.append(candidate.uid)

        if outcome.changes:
            first = outcome.changes[0]
            extra = len(outcome.changes) - 1
            title = f"{first.participant_name} {STATUS_VERBS_RU[first.status]}"
            body = f"Встреча «{first.booking_title}»"
            if extra > 0:
                body += f" (и ещё {extra} встреч серии)"
            if first.creator_id is not None:
                publish = await create_notification(
                    db,
                    redis,
                    user_id=first.creator_id,
                    type="meeting_rsvp",
                    title=title,
                    body=body,
                    link="/meetings",
                )
                publish_callbacks.append(publish)
            for change in outcome.changes:
                sse_events.append(
                    (
                        change.booking_id,
                        change.room_ids,
                        change.date_str,
                    )
                )

    # Коммитит caller (async with session.begin()); до commit — только flush'ы.
    return counters, processed_uids, publish_callbacks, sse_events


async def poll_meetings_rsvp(ctx: dict) -> dict:
    """Опросить общий ящик, применить RSVP-ответы, удалить обработанные письма."""
    redis: Redis | None = ctx.get("redis")
    if redis is None:
        return {"skipped": "no_redis"}

    reason = _gates_open()
    if reason is not None:
        return {"skipped": reason}

    settings = load_email_settings()
    if not imap_configured(settings):
        return {"skipped": "imap_not_configured"}

    # Interval-guard: cron дёргает каждые 30 с, реальный интервал — 60 с.
    last = await redis.get(RSVP_LAST_POLL_KEY)
    if last:
        if isinstance(last, bytes):
            last = last.decode("utf-8", errors="ignore")
        try:
            last_dt = datetime.fromisoformat(str(last))
            if datetime.now(UTC) - last_dt < timedelta(seconds=RSVP_POLL_INTERVAL_SECONDS):
                return {"skipped": "interval_not_elapsed"}
        except ValueError:
            pass  # битое значение — идём дальше

    lock_token = await _acquire_lock(redis, RSVP_POLL_LOCK_KEY, RSVP_POLL_LOCK_TTL)
    if lock_token is None:
        return {"skipped": "lock_held"}

    try:
        await redis.set(RSVP_LAST_POLL_KEY, datetime.now(UTC).isoformat())
        candidates = await fetch_reply_candidates(settings)
        if not candidates:
            return {"processed": 0}

        async with AsyncSessionLocal() as db, db.begin():
            (
                counters,
                processed_uids,
                publish_callbacks,
                sse_events,
            ) = await _ingest_batch(db, redis, candidates)

        # После commit: доставить уведомления (колокольчик) и SSE-события.
        for publish in publish_callbacks:
            await publish()
        for booking_id, room_ids, date_str in sse_events:
            await publish_meeting_event(
                redis,
                action="rsvp",
                booking_id=booking_id,
                room_ids=room_ids,
                date_str=date_str,
            )

        # Обработанные REPLY убираем из ящика (в т.ч. дубликаты и not_found —
        # дедуп по message_id не даст им обрабатываться повторно, но ящик
        # не должен копить календарный мусор).
        deleted = await delete_reply_messages(settings, processed_uids)

        logger.info("meetings.rsvp.poll_done", **counters, deleted=deleted)
        return {"processed": len(candidates), **counters, "deleted": deleted}
    except Exception as exc:
        logger.exception("meetings.rsvp.poll_failed", error=str(exc))
        return {"error": type(exc).__name__}
    finally:
        await _release_lock(redis, RSVP_POLL_LOCK_KEY, lock_token)
