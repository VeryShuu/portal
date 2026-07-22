"""Agent read-state for helpdesk tickets (миграция 080).

Подсветка непрочитанных заявок в инбоксе агента: тикет «непрочитан» для агента,
если существует входящее сообщение (ответ заявителя) новее, чем
``last_seen_at`` этого агента на тикете.

Контракт «непрочитанности» (фиксирован решением владельца):
* учитываются только ``HelpdeskMessage`` с ``direction='inbound'`` — то есть
  ответы заявителя (через веб-форму или email-ingress);
* ответы других агентов (``direction='outbound'``) и свои собственные НЕ
  считаются — агент и так их видел.

Точка «прочитано» — открытие карточки тикета агентом: ``POST /tickets/{id}/read``
вызывает :func:`mark_ticket_seen` (UPSERT ``last_seen_at = NOW()``).

Marker-таблица :class:`~app.models.helpdesk.HelpdeskTicketRead` — одна строка
на пару ``(ticket_id, user_id)``. ``ON DELETE CASCADE`` на обеих FK → cleanup
не нужен (архивация/удаление тикета или аккаунта чистят автоматически).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket, HelpdeskTicketRead

# Константы контракта «непрочитанности». Вынесены, чтобы тесты и запросы
# ссылались на единый источник истины (защита от регрессии).
INBOUND_DIRECTION = "inbound"  # от заявителя (для агентского unread-контракта)
OUTBOUND_DIRECTION = "outbound"  # от агента (для заявительского unread-контракта)

# Sentinel «никогда не видел»: ``datetime`` через ``func.coalesce`` передаётся
# как типизированный bind-parameter TIMESTAMPTZ (а не VARCHAR, как было с
# ``literal("-infinity")`` — там SQLAlchemy выводил VARCHAR, и Postgres падал
# на ``TIMESTAMPTZ > VARCHAR``). Любая реальная ``created_at`` новее 1970-го —
# модуль helpdesk заведён в 2026, поэтому эпоха надёжно «до всего».
EPOCH_SENTINEL = datetime(1970, 1, 1, tzinfo=UTC)


async def mark_ticket_seen(
    db: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> datetime:
    """Записать «агент ``user_id`` видел тикет ``ticket_id`` в момент ``now``».

    UPSERT по ``(ticket_id, user_id)``: если строки нет — INSERT с ``last_seen_at
    = now``; если есть — UPDATE только ``last_seen_at`` (``created_at`` не
    трогаем — это метка первого просмотра, полезна для аналитики). Повторное
    открытие карточки = no-op по смыслу (просто более свежий ``last_seen_at``).

    НЕ делает ``db.commit()`` — caller (роутер) контролирует транзакцию. Это
    согласовано с остальными helpdesk-сервисами (outbox-инвариант AGENTS.md):
    единый commit в роутере.

    Возвращает ``last_seen_at`` (для ответа API).
    """
    seen_at = now or datetime.now(UTC)
    # ``ON CONFLICT (ticket_id, user_id)`` — по индексу ``uq_helpdesk_ticket_reads_ticket_user``
    # (UNIQUE INDEX, не CONSTRAINT — миграция 080 создаёт именно индекс). Для
    # индексов используется ``index_elements`` (список колонок), а не ``constraint=``
    # (последнее работает только для ``UNIQUE CONSTRAINT`` и падает с
    # ``UndefinedObjectError: constraint ... does not exist``).
    stmt = (
        pg_insert(HelpdeskTicketRead)
        .values(ticket_id=ticket_id, user_id=user_id, last_seen_at=seen_at)
        .on_conflict_do_update(
            index_elements=["ticket_id", "user_id"],
            set_={"last_seen_at": seen_at},
        )
    )
    await db.execute(stmt)
    return seen_at


async def has_unread_requester_messages(
    db: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime | None = None,
    direction: str = INBOUND_DIRECTION,
) -> bool:
    """Есть ли в тикете непрочитанные сообщения указанного направления.

    По умолчанию ``direction='inbound'`` (агентский контракт — ответы
    заявителя). Для заявителя передавайте ``direction='outbound'`` (ответы
    агентов) — зеркальная семантика «что считать непрочитанным».

    ``True`` если существует сообщение указанного направления с
    ``created_at > COALESCE(last_seen_at, EPOCH)``.
    Если строки read нет — берётся ``EPOCH_SENTINEL`` (т.е. **любое** сообщение
    делает тикет непрочитанным, даже месячной давности — пользователь его
    действительно не открывал в этом UI).

    ``now`` зарезервирован для future-use (например, «читать только активные
    тикеты»); сейчас не нужен — контракта «новее last_seen_at» достаточно.
    """
    del now  # placeholder для future-use (см. docstring); не используется.
    # Подзапрос: ``last_seen_at`` этого пользователя (или NULL, если строки нет).
    last_seen_subq = (
        select(HelpdeskTicketRead.last_seen_at)
        .where(
            HelpdeskTicketRead.ticket_id == ticket_id,
            HelpdeskTicketRead.user_id == user_id,
        )
        .scalar_subquery()
    )
    # ``func.coalesce`` с datetime-``EPOCH_SENTINEL`` → bind-parameter TIMESTAMPTZ
    # (а не VARCHAR, как у ``literal("-infinity")``). См. комментарий у константы.
    unread_exists = (
        select(HelpdeskMessage.id)
        .where(
            HelpdeskMessage.ticket_id == ticket_id,
            HelpdeskMessage.direction == direction,
            HelpdeskMessage.created_at > func.coalesce(last_seen_subq, EPOCH_SENTINEL),
        )
        .exists()
    )
    res = await db.execute(select(unread_exists))
    return bool(res.scalar_one())


async def enrich_with_unread(
    db: AsyncSession,
    *,
    tickets: Sequence[HelpdeskTicket],
    user_id: uuid.UUID,
    direction: str = INBOUND_DIRECTION,
) -> dict[uuid.UUID, bool]:
    """Для списка тикетов одним запросом вернуть ``{ticket_id: unread}``.

    Решает N+1-проблему: если бы :func:`has_unread_requester_messages` звалась
    на каждый тикет отдельно, страница из 20+20 тикетов делала бы 40 запросов.
    Здесь — один SELECT: для каждого ``ticket_id`` проверяем EXISTS публичного
    сообщения указанного направления новее ``last_seen_at`` (или ``EPOCH`` если
    пользователь тикет не открывал).

    По умолчанию ``direction='inbound'`` (агентский инбокс — ответы заявителя).
    Для заявителя передавайте ``direction='outbound'`` (ответы агентов).

    ``tickets`` — уже загруженный список (из :func:`list_agent_tickets` или
    :func:`list_my_tickets`); берём оттуда только ``id``. Возвращает map, чтобы
    сериализатор :func:`app.api.helpdesk._common.ticket_to_list_out` делал
    O(1)-lookup, а не N-проходов.
    """
    ticket_ids = [t.id for t in tickets]
    if not ticket_ids:
        return {}

    # LEFT JOIN reads (одна строка на пару ticket×user из-за UNIQUE) —
    # ``reads.last_seen_at`` будет NULL для тикетов, которые агент не открывал.
    # Дальше фильтруем сообщения и проверяем «есть ли хоть одно новое».
    last_seen_subq = (
        select(HelpdeskTicketRead.last_seen_at)
        .where(HelpdeskTicketRead.user_id == user_id)
        .correlate(HelpdeskMessage)
        .where(HelpdeskTicketRead.ticket_id == HelpdeskMessage.ticket_id)
        .scalar_subquery()
    )
    # Для каждого ticket_id: True если COUNT(inbound, созданных после
    # last_seen_at) > 0. Используем COUNT + GROUP BY + фильтр, чтобы получить
    # ровно map {ticket_id: bool} одним запросом.
    stmt = (
        select(
            HelpdeskMessage.ticket_id.label("ticket_id"),
            func.count().label("unread_count"),
        )
        .where(
            HelpdeskMessage.ticket_id.in_(ticket_ids),
            HelpdeskMessage.direction == direction,
            HelpdeskMessage.created_at > func.coalesce(last_seen_subq, EPOCH_SENTINEL),
        )
        .group_by(HelpdeskMessage.ticket_id)
    )
    res = await db.execute(stmt)
    unread_ticket_ids: set[uuid.UUID] = set()
    for row in res.all():
        # row[0] → ticket_id (первая колонка SELECT). Универсальнее, чем
        # ``row.tuple()`` — работает и с SQLAlchemy ``Row``, и с plain tuple
        # в тестах. unread_count (row[1]) не нужен: фильтр в WHERE пропускает
        # только новые сообщения, COUNT группы ≥ 1 (любая строка = непрочитан).
        tid = row[0]
        unread_ticket_ids.add(tid)

    # Тикеты без новых inbound сообщений → False. Возвращаем map для ВСЕХ
    # входных тикетов, чтобы сериализатор делал простой ``map[t.id]`` без
    # обработки KeyError для прочитанных тикетов.
    return {tid: (tid in unread_ticket_ids) for tid in ticket_ids}
