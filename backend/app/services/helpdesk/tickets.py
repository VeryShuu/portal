"""Ticket lifecycle for the requester web-flow (Helpdesk Этап 2).

Создание тикета и списочное чтение «своих» тикетов. Инвариант первого
сообщения (ТЗ §4.3.1): при создании всегда создаётся первая запись в
``helpdesk_messages`` (``direction=inbound``, ``visibility=public``), а поля
``helpdesk_tickets.description`` дублируют её текст для быстрых списков и
поиска.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket
from app.models.user import User
from app.schemas.helpdesk import TicketCreateIn
from app.services.helpdesk.lifecycle import IllegalTransitionError, agent_set_status

logger = get_logger(__name__)


async def _try_enqueue_created_email(db: AsyncSession, *, ticket: HelpdeskTicket) -> None:
    """Best-effort: поставить письмо «заявка зарегистрирована» в outbox.

    Только при сконфигурированном mailbox (есть ``support_domain``). Без mailbox
    (web-only helpdesk) — no-op: заявку можно создать, но подтверждение на email
    не уходит (in-app уведомление агентам остаётся). Сбой не роняет создание
    заявки (логируется warning).
    """
    try:
        from app.services.helpdesk.outbound import (
            enqueue_created_email,
            load_mailbox,
            support_domain,
        )

        mailbox = await load_mailbox(db)
        if mailbox is None or not support_domain(mailbox):
            return
        await enqueue_created_email(db, ticket=ticket, mailbox=mailbox)
    except Exception as exc:
        logger.warning("helpdesk.created_email_enqueue_failed", error=str(exc))


async def create_ticket(
    db: AsyncSession,
    *,
    user: User,
    payload: TicketCreateIn,
    files: list | None = None,
) -> HelpdeskTicket:
    """Создать заявку от авторизованного пользователя (``source=web``).

    Транзакционно создаёт тикет и его первое public-inbound сообщение.
    ``requester_email``/``requester_name`` берутся из аккаунта пользователя —
    для web-flow гость не предусмотрен. ``files`` (опционально, Этап 4) —
    список ``UploadFile``: пишутся в локальную папку тикета тем же паттерном,
    что и feedback (FS-запись до commit в пределах сервисной функции).
    """
    ticket = HelpdeskTicket(
        subject=payload.subject,
        description=payload.description,
        description_html=payload.description_html,
        status="new",
        source="web",
        requester_user_id=user.id,
        requester_email=user.email,
        requester_name=user.full_name,
    )
    db.add(ticket)
    await db.flush()  # нужен ticket.id + ticket.number перед созданием сообщения

    first_message = HelpdeskMessage(
        ticket_id=ticket.id,
        author_user_id=user.id,
        author_email=user.email,
        author_name=user.full_name,
        direction="inbound",
        visibility="public",
        body_text=payload.description,
        # ``body_html`` = ``description_html`` (sanitized в роутере): письмо
        # агентам (``render_new_ticket_agent_email``) читает ``first_message.body_html``
        # с fallback на plain — форматирование заявки попадёт в письмо автоматически,
        # без правок email-кода. В ленте портала рендерится через ``TicketMessageList``.
        body_html=payload.description_html,
        source="web",
        # Явный ``created_at`` (Python-время) — см. комментарий в
        # ``add_requester_reply``: server_default ``NOW()`` фиксирует
        # transaction-start time и ломает unread-семантику в тестах.
        created_at=datetime.now(UTC),
    )
    db.add(first_message)
    await db.flush()  # нужен first_message.id для привязки вложений

    if files:
        from app.services.helpdesk.attachments import upload_attachments

        await upload_attachments(
            db,
            ticket=ticket,
            message_id=first_message.id,
            files=files,
            actor=user,
        )

    # Backfill inline-картинок из draft-attachments: rich-редактор формы создания
    # грузит картинки через ``POST /draft-attachments`` (нет ``ticket_id`` до
    # сохранения) и вставляет draft-URL в ``description_html``. Здесь переносим
    # файлы в постоянное хранилище ``TKT-{number}/inline/`` и переписываем ``src``
    # на ``/tickets/{id}/inline-media/{name}`` (serve-endpoint ответов). Мутирует
    # ``ticket.description_html`` И ``first_message.body_html`` в той же
    # транзакции (атомарно с созданием тикета). Best-effort: битые/чужие draft'ы
    # остаются как есть (``src`` не переписывается) — заявка создаётся.
    if payload.description_html:
        from app.services.helpdesk.drafts import backfill_draft_images

        new_html = await backfill_draft_images(
            db,
            ticket=ticket,
            message_id=first_message.id,
            html=payload.description_html,
            user=user,
        )
        if new_html is not None:
            ticket.description_html = new_html
            first_message.body_html = new_html

    # Email заявителю «заявка зарегистрирована» — только при сконфигурированном
    # mailbox (outbox ``kind=helpdesk``, входит в email-тред тикета). Ставится
    # в ту же транзакцию, что и создание тикета (outbox-инвариант AGENTS.md):
    # письмо коммитится атомарно с тикетом+сообщением. Best-effort: сбой enqueue
    # (например, нет mailbox) не блокирует создание заявки.
    await _try_enqueue_created_email(db, ticket=ticket)

    await db.commit()
    await db.refresh(ticket)
    # Перечитываем с eager-load сообщений, чтобы возвращать полный объект.
    return await fetch_ticket_for_user(db, ticket_id=ticket.id, user_id=user.id)  # type: ignore[return-value]


async def count_my_tickets(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    status_filter: str | None,
    unassigned: bool = False,
    assigned: bool = False,
    active_only: bool = False,
) -> int:
    conditions = [HelpdeskTicket.requester_user_id == user_id]
    if status_filter:
        conditions.append(HelpdeskTicket.status == status_filter)
    # Активные тикеты (new/open/pending) — closed скрыт в архиве заявителя.
    # Используется двухблочным my-tickets («ожидают принятия» / «в работе»),
    # чтобы не тащить закрытые в основной вид. Игнорируется, если задан
    # конкретный status_filter (он точнее) — симметрично _agent_filter_conditions.
    elif active_only:
        conditions.append(HelpdeskTicket.status.in_(_ACTIVE_STATUSES))
    # Деление на «неназначенные» / «назначенные» для двухблочного вида my-tickets
    # (по образцу _agent_filter_conditions). Взаимоисключающие через elif —
    # как у агентов (нельзя одновременно unassigned+assigned).
    if unassigned:
        conditions.append(HelpdeskTicket.assignee_user_id.is_(None))
    elif assigned:
        conditions.append(HelpdeskTicket.assignee_user_id.is_not(None))
    res = await db.execute(select(func.count()).select_from(HelpdeskTicket).where(*conditions))
    return int(res.scalar_one())


# Активные статусы (new/open/pending) — «открытые» тикеты, не закрытые и не в
# архиве. Используется для счётчиков в меню (заявитель видит «мои открытые»,
# агент — «мои назначенные в работе»). ``closed`` исключается.
_ACTIVE_STATUSES = ("new", "open", "pending")


async def count_my_active_tickets(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Сколько тикетов у пользователя в активных статусах (new/open/pending).

    Для бейджа в меню пункта «Поддержка» — быстрый сигнал «у вас N открытых
    заявок». ``closed`` исключён (закрытые — архивная история). Один запрос
    ``count(*)``, без join'ов, без пагинации.
    """
    res = await db.execute(
        select(func.count())
        .select_from(HelpdeskTicket)
        .where(
            HelpdeskTicket.requester_user_id == user_id,
            HelpdeskTicket.status.in_(_ACTIVE_STATUSES),
        )
    )
    return int(res.scalar_one())


async def count_assigned_active_tickets(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Сколько активных тикетов назначено на агента (assignee = user_id).

    Для бейджа в меню пункта «Инбокс поддержки» — «в работе у меня N заявок».
    Не включает неназначенные (это отдельная метрика инбокса). Активные
    статусы (new/open/pending), ``closed`` исключён.
    """
    res = await db.execute(
        select(func.count())
        .select_from(HelpdeskTicket)
        .where(
            HelpdeskTicket.assignee_user_id == user_id,
            HelpdeskTicket.status.in_(_ACTIVE_STATUSES),
        )
    )
    return int(res.scalar_one())


async def list_my_tickets(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    status_filter: str | None,
    limit: int,
    offset: int,
    unassigned: bool = False,
    assigned: bool = False,
    active_only: bool = False,
) -> Sequence[HelpdeskTicket]:
    """Список тикетов инициатора. ``assignee_name`` подтягивается через
    relationship; для списков достаточно не загружать сообщения.

    ``unassigned``/``assigned`` — деление на «ожидают принятия» (без агента) и
    «в работе у специалиста» (с назначенным агентом) для двухблочного вида
    my-tickets. Взаимоисключающие через ``elif`` (как у агентов).

    ``active_only`` — скрыть closed (только new/open/pending). Симметрично
    ``_agent_filter_conditions``. Игнорируется при явном ``status_filter``.
    """
    conditions = [HelpdeskTicket.requester_user_id == user_id]
    if status_filter:
        conditions.append(HelpdeskTicket.status == status_filter)
    elif active_only:
        conditions.append(HelpdeskTicket.status.in_(_ACTIVE_STATUSES))
    if unassigned:
        conditions.append(HelpdeskTicket.assignee_user_id.is_(None))
    elif assigned:
        conditions.append(HelpdeskTicket.assignee_user_id.is_not(None))
    res = await db.execute(
        select(HelpdeskTicket)
        .where(*conditions)
        .options(
            selectinload(HelpdeskTicket.assignee),
            selectinload(HelpdeskTicket.requester_user),
        )
        .order_by(HelpdeskTicket.last_activity_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().unique().all()


async def fetch_ticket_for_user(
    db: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
) -> HelpdeskTicket | None:
    """Свой тикет с сообщениями. Фильтр по ``requester_user_id`` — основа ACL
    «только свои» (ТЗ §4.5); ``internal``-сообщения отсекаются на уровне
    сериализации (не здесь). Вложения сообщений подгружаем eagerly, иначе
    async-доступ к relationship в mapper'е поднимет MissingGreenlet."""
    from app.models.helpdesk import HelpdeskMessage

    res = await db.execute(
        select(HelpdeskTicket)
        .where(
            HelpdeskTicket.id == ticket_id,
            HelpdeskTicket.requester_user_id == user_id,
        )
        .options(
            selectinload(HelpdeskTicket.messages),
            selectinload(HelpdeskTicket.messages).selectinload(HelpdeskMessage.attachments),
            selectinload(HelpdeskTicket.assignee),
        )
    )
    return res.scalars().unique().one_or_none()


# ---------------------------------------------------------------------------
# Agent view (Этап 3)
# ---------------------------------------------------------------------------


async def count_agent_tickets(
    db: AsyncSession,
    *,
    status_filter: str | None = None,
    assignee_id: uuid.UUID | None = None,
    unassigned: bool = False,
    source: str | None = None,
    query: str | None = None,
    active_only: bool = False,
    assigned: bool = False,
) -> int:
    """Количество тикетов по фильтрам агентского инбокса."""
    conditions = _agent_filter_conditions(
        status_filter=status_filter,
        assignee_id=assignee_id,
        unassigned=unassigned,
        source=source,
        query=query,
        active_only=active_only,
        assigned=assigned,
    )
    res = await db.execute(select(func.count()).select_from(HelpdeskTicket).where(*conditions))
    return int(res.scalar_one())


async def list_agent_tickets(
    db: AsyncSession,
    *,
    status_filter: str | None = None,
    assignee_id: uuid.UUID | None = None,
    unassigned: bool = False,
    source: str | None = None,
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
    active_only: bool = False,
    assigned: bool = False,
) -> Sequence[HelpdeskTicket]:
    """Список тикетов для агентского инбокса со всеми фильтрами ТЗ §4.4."""
    conditions = _agent_filter_conditions(
        status_filter=status_filter,
        assignee_id=assignee_id,
        unassigned=unassigned,
        source=source,
        query=query,
        active_only=active_only,
        assigned=assigned,
    )
    res = await db.execute(
        select(HelpdeskTicket)
        .where(*conditions)
        .options(
            selectinload(HelpdeskTicket.assignee),
            selectinload(HelpdeskTicket.requester_user),
        )
        .order_by(HelpdeskTicket.last_activity_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().unique().all()


def _agent_filter_conditions(
    *,
    status_filter: str | None,
    assignee_id: uuid.UUID | None,
    unassigned: bool,
    source: str | None,
    query: str | None,
    active_only: bool = False,
    assigned: bool = False,
) -> list:
    conditions: list = []
    if status_filter:
        conditions.append(HelpdeskTicket.status == status_filter)
    # Активные тикеты (new/open/pending) — closed скрыт в архиве.
    # Используется двухблочным инбоксом агента (нижний блок «В работе»),
    # чтобы не тащить закрытые в основной вид. Игнорируется, если задан
    # конкрет status_filter (он точнее).
    elif active_only:
        conditions.append(HelpdeskTicket.status.in_(("new", "open", "pending")))
    if assignee_id is not None:
        conditions.append(HelpdeskTicket.assignee_user_id == assignee_id)
    if unassigned:
        conditions.append(HelpdeskTicket.assignee_user_id.is_(None))
    elif assigned:
        # Противоположность unassigned: только назначенные (assignee IS NOT NULL).
        # Нужно для режима «Все назначенные» в инбоксе — иначе вернутся и
        # неназначенные (которые уже в верхнем блоке «Новые заявки»).
        conditions.append(HelpdeskTicket.assignee_user_id.is_not(None))
    if source:
        conditions.append(HelpdeskTicket.source == source)
    if query:
        query = query.strip()
    if query:
        # Полнотекстовый поиск (миграция 078) по конфигурации russian_hunspell
        # (как в KB-статьях/новостях). websearch_to_tsquery поддерживает
        # операторы: "точная фраза", OR, -исключение. Экранирования не требует
        # (в отличие от ilike).
        # Ищем по: subject+description тикета (search_tsvector) ИЛИ по телам
        # ответов (EXISTS по helpdesk_messages.body_tsvector). Email — через
        # ilike: адреса плохо матчатся tsquery (@/точки/домены).
        tsq = func.websearch_to_tsquery("russian_hunspell", query)
        conditions.append(
            or_(
                HelpdeskTicket.search_tsvector.op("@@")(tsq),
                # Матч по телу любого ответа/заметки тикета.
                select(HelpdeskMessage.id)
                .where(
                    HelpdeskMessage.ticket_id == HelpdeskTicket.id,
                    HelpdeskMessage.body_tsvector.op("@@")(tsq),
                )
                .exists(),
                HelpdeskTicket.requester_email.ilike(f"%{query}%"),
            )
        )
    return conditions


async def fetch_ticket_for_agent(
    db: AsyncSession, *, ticket_id: uuid.UUID
) -> HelpdeskTicket | None:
    """Тикет для агентского view — все сообщения (включая internal),
    assignee и requester. Вложения сообщений подгружаем eagerly для
    сериализации (async-доступ к lazy relationship поднимает MissingGreenlet)."""
    from app.models.helpdesk import HelpdeskMessage

    res = await db.execute(
        select(HelpdeskTicket)
        .where(HelpdeskTicket.id == ticket_id)
        .options(
            selectinload(HelpdeskTicket.messages),
            selectinload(HelpdeskTicket.messages).selectinload(HelpdeskMessage.attachments),
            selectinload(HelpdeskTicket.assignee),
            selectinload(HelpdeskTicket.requester_user),
        )
    )
    return res.scalars().unique().one_or_none()


async def resolve_requester_user(db: AsyncSession, *, ticket: HelpdeskTicket) -> User | None:
    """Найти пользователя-заявителя тикета для построения профиля.

    * Если у тикета есть ``requester_user_id`` — возвращаем eagerly-loaded
      ``ticket.requester_user`` (без доп. запроса к БД).
    * Иначе (гостевая email-заявка) — fallback-поиск сотрудника по
      ``LOWER(users.email) = LOWER(ticket.requester_email)`` среди не удалённых.
      Не найден → ``None`` (блок профиля не отрисовывается).
    """
    if ticket.requester_user_id is not None:
        return ticket.requester_user
    if not ticket.requester_email:
        return None
    res = await db.execute(
        select(User).where(
            func.lower(User.email) == ticket.requester_email.lower(),
            User.deleted_at.is_(None),
        )
    )
    return res.scalars().one_or_none()


async def assign_ticket(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    assignee_id: uuid.UUID,
) -> HelpdeskTicket:
    """Назначить ответственного. ``new → open`` (ТЗ §4.2.1), фиксация
    ``assigned_at``. Реассайн разрешён (предыдущий assignee заменяется).

    Внимание (outbox-инвариант, AGENTS.md): НЕ делает ``db.commit()`` — только
    мутирует объект в сессии. Caller обязан поставить outbox-запись (письмо о
    назначении) в той же транзакции и сделать единый ``commit``. Раньше commit
    был здесь, а outbox — отдельным commit в роутере (нарушение инварианта)."""
    now = datetime.now(UTC)
    ticket.assignee_user_id = assignee_id
    ticket.assigned_at = now
    if ticket.status == "new":
        ticket.status = "open"
    ticket.last_activity_at = now
    return ticket


async def is_active_helpdesk_agent(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
    """Является ли ``user_id`` активным helpdesk-агентом (живой аккаунт).

    Used by ``POST /tickets/{id}/assign`` для валидации таргета: передать заявку
    можно только действующему агенту техподдержки. Суперсет admin'ов здесь не
    подразумевается (админ без ``helpdesk_agents``-членства не считается агентом
    для цели назначения — но это редко встречается, т.к. админ обычно назначает
    сам себя через ``take``).

    Возвращает ``bool``, без проброса исключений — caller решает, что делать при
    ``False`` (роутер транслирует в 404, чтобы не раскрывать детали членства)."""
    from app.models.helpdesk import HelpdeskAgent

    res = await db.execute(
        select(HelpdeskAgent.user_id)
        .join(User, User.id == HelpdeskAgent.user_id)
        .where(HelpdeskAgent.user_id == user_id, User.deleted_at.is_(None))
    )
    return res.first() is not None


async def list_assignable_agents(db: AsyncSession) -> list[tuple[uuid.UUID, str | None, str]]:
    """Активные helpdesk-агенты (с живым аккаунтом) для списка смены
    ответственного в карточке тикета.

    Возвращает список ``(user_id, full_name, email)`` — без флагов уведомлений
    (PII-минимизация: агенту для смены ответственного достаточно знать, кому
    можно передать заявку). JOIN users — единый источник правды о живом аккаунте
    (``deleted_at IS NULL``). Сортировка — по ФИО (как в admin-списке агентов).
    На фронте рендерится простым списком в popover (без поиска — агентов
    поддержки обычно ~5 человек)."""
    from app.models.helpdesk import HelpdeskAgent

    res = await db.execute(
        select(User.id, User.full_name, User.email)
        .join(HelpdeskAgent, HelpdeskAgent.user_id == User.id)
        .where(User.deleted_at.is_(None))
        .order_by(User.full_name)
    )
    return [(r[0], r[1], r[2]) for r in res.all()]


async def change_status(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    target: str,
    actor: User,
) -> HelpdeskTicket:
    """Ручной переход статуса агентом/админом по статус-машине (ТЗ §4.2.1).

    Закрытие фиксирует ``closed_at``/``closed_by_user_id``; переход из
    ``closed`` (reopen) здесь запрещён — для него отдельный endpoint.
    ``IllegalTransitionError`` пробрасывается наверх (роутер транслирует в 409).
    """
    result = agent_set_status(ticket.status, target)

    now = datetime.now(UTC)
    if result.set_closed:
        ticket.closed_at = now
        ticket.closed_by_user_id = actor.id
    ticket.status = result.status
    ticket.last_activity_at = now
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def reopen_ticket(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
) -> HelpdeskTicket:
    """Reopen закрытого тикета агентом/админом: ``closed → open`` с очисткой
    ``closed_*`` (ТЗ §4.2.1). Reopen архивного тикета невозможен — он уже
    удалён из основной таблицы."""
    if ticket.status != "closed":
        raise IllegalTransitionError(
            current=ticket.status,
            allowed=["closed"],  # reopen только из closed
        )
    now = datetime.now(UTC)
    ticket.status = "open"
    ticket.closed_at = None
    ticket.closed_by_user_id = None
    ticket.last_activity_at = now
    await db.commit()
    await db.refresh(ticket)
    return ticket


# ---------------------------------------------------------------------------
# Guest linking (Этап 5, ТЗ §4.5)
# ---------------------------------------------------------------------------


async def link_guest_tickets(db: AsyncSession, *, user_id: uuid.UUID, email: str) -> int:
    """Привязать гостевые тикеты (``requester_user_id IS NULL``) с совпадающим
    email к только что материализованному аккаунту (ТЗ §4.5). Матчинг по
    ``LOWER(requester_email) = LOWER(user.email)`` (bind-параметр, не
    интерполяция). Идемпотентно: повторные логины — no-op.

    Вызывается из OIDC-callback после ``_upsert_user`` (до commit), в local.py
    точки вызова нет (там логин без upsert'а). Возвращает кол-во привязанных
    тикетов.
    """
    res = await db.execute(
        select(HelpdeskTicket).where(
            HelpdeskTicket.requester_user_id.is_(None),
            func.lower(HelpdeskTicket.requester_email) == email.lower(),
        )
    )
    tickets = res.scalars().all()
    for t in tickets:
        t.requester_user_id = user_id
    return len(tickets)
