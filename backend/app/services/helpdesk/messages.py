"""Adding messages to a ticket thread (Helpdesk Этап 2).

Ответ инициатора — всегда ``direction=inbound`` и ``visibility=public``
(внутренние заметки и outbound-ответы агентов появляются на этапе 3).
Согласно ТЗ §4.2.1, ответ клиента переводит тикет:

* ``pending`` → ``open`` (клиент «проснулся» — ждём агента);
* ``new``/``open``/``closed`` остаются как есть на этом этапе (``closed``
  реопенится только агентом/админом или auto-reopen window — этап 3/5).

Во всех случаях обновляется ``last_activity_at``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.sanitize import sanitize_html
from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket
from app.models.user import User
from app.schemas.helpdesk import HelpdeskVisibility, MessageCreateIn

# Статусы, из которых ответ клиента реопенит тикет в ``open`` (ТЗ §4.2.1).
# ``closed`` реопенится отдельно — только в окне HELPDESK_REOPEN_WINDOW_DAYS
# (см. requester_reply_on_closed в lifecycle). ``resolved`` упразднён (079).
_REQUESTER_REOPEN_STATUSES = frozenset({"pending"})


def normalize_message_bodies(
    body_text: str | None,
    body_html: str | None,
) -> tuple[str, str | None]:
    """Нормализовать тело сообщения: sanitize HTML + деривация plain.

    Логика (для rich-редактора helpdesk — фронт шлёт HTML из TipTap):
    * ``body_html`` (если есть) прогоняется через ``sanitize_html`` (nh3) —
      защита от XSS (заявитель — неконтролируемая сторона, как email-ingress).
      Сохраняет ``figure``/``figcaption``/``img`` (для inline-картинок) и
      относительные URL (``/api/v1/helpdesk/.../inline-media/...``).
    * ``body_text`` (plain) — если пуст, деривируется из sanitized HTML через
      ``html_to_plain`` (снятие тегов). Нужен для email-треда (``text/plain``
      часть письма) и fallback-отображения в ленте при отсутствии HTML.
    * Возвращает ``(body_text, body_html)``. ``body_html`` — ``None``, если
      исходный был пуст (колонка nullable, не храним пустую строку).

    Не валидирует непустоту — это ответственность роутера (422 если оба пусты).
    """
    from app.services.helpdesk.email_quote import html_to_plain

    clean_html = sanitize_html(body_html) if body_html else None
    if body_text and body_text.strip():
        plain = body_text
    elif clean_html:
        plain = html_to_plain(clean_html)
    else:
        plain = ""
    return plain, clean_html or None


def _make_outbound_message_id(ticket_number: int, support_domain: str) -> str:
    """Канонический ``Message-ID`` исходящего письма (ТЗ §1.3.3):
    ``<tkn-{ticket_number}-{message_uuid}@{support_domain}>``.

    ``message_uuid`` — свежий ``uuid.uuid4()`` (НЕ первичный ключ HelpdeskMessage,
    который генерируется в БД через ``gen_random_uuid()``). Этот uuid хранится в
    ``HelpdeskMessage.email_message_id`` и используется для threading входящих
    ответов (``In-Reply-To``/``References`` матчятся по этому полю)."""
    message_uuid = uuid.uuid4()
    return f"<tkn-{ticket_number}-{message_uuid}@{support_domain}>"


async def add_requester_reply(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    user: User,
    payload: MessageCreateIn,
    files: list | None = None,
) -> HelpdeskMessage:
    """Добавить ответ инициатора в свой тикет.

    ``ticket`` уже загружен и ACL-проверен роутером
    (``fetch_ticket_for_user``). Метод форсирует ``inbound``/``public``
    независимо от тела запроса — инициатор не может создать внутреннюю
    заметку или outbound-сообщение. ``files`` (опционально, Этап 4) —
    локальные вложения, привязываемые к новому сообщению.
    """
    now = datetime.now(UTC)

    message = HelpdeskMessage(
        ticket_id=ticket.id,
        author_user_id=user.id,
        author_email=user.email,
        author_name=user.full_name,
        direction="inbound",
        visibility="public",
        body_text=payload.body_text,
        body_html=payload.body_html,
        source="web",
    )
    db.add(message)
    await db.flush()  # нужен message.id для привязки вложений

    if files:
        from app.services.helpdesk.attachments import upload_attachments

        await upload_attachments(db, ticket=ticket, message_id=message.id, files=files, actor=user)

    if ticket.status in _REQUESTER_REOPEN_STATUSES:
        ticket.status = "open"

    ticket.last_activity_at = now

    await db.commit()
    await db.refresh(message)
    # Подгружаем attachments для сериализации (lazy в async поднимает
    # MissingGreenlet) — отдельным запросом, чтобы не зависеть от состояния
    # сессии после upload_attachments.
    await _eager_load_attachments(db, message)
    return message


async def _eager_load_attachments(db: AsyncSession, message: HelpdeskMessage) -> None:
    """Перезагрузить ``message.attachments`` через selectinload (для mapper'а)."""
    res = await db.execute(
        select(HelpdeskMessage)
        .options(selectinload(HelpdeskMessage.attachments))
        .where(HelpdeskMessage.id == message.id)
    )
    fresh = res.scalars().unique().one_or_none()
    if fresh is not None:
        message.attachments = fresh.attachments


async def fetch_ticket_with_messages(
    db: AsyncSession, *, ticket_id: uuid.UUID
) -> HelpdeskTicket | None:
    """Загрузить тикет с сообщениями (используется роутером после добавления
    ответа для возврата обновлённого таймлайна)."""
    res = await db.execute(
        select(HelpdeskTicket)
        .where(HelpdeskTicket.id == ticket_id)
        .options(selectinload(HelpdeskTicket.messages))
    )
    return res.scalars().unique().one_or_none()


# ---------------------------------------------------------------------------
# Agent reply (Этап 3)
# ---------------------------------------------------------------------------


async def add_agent_reply(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    agent: User,
    payload: MessageCreateIn,
    files: list | None = None,
    support_domain: str | None = None,
) -> HelpdeskMessage:
    """Ответ агента — ``direction=outbound``. ``visibility`` из payload:
    ``public`` (виден клиенту, переводит тикет в ``pending`` и уйдёт в
    email_outbox при наличии ``support_domain``) или ``internal`` (заметка
    агентов, статус не меняет, на email не уходит). ``files`` (опционально,
    Этап 4) — локальные вложения к ответу.

    ``support_domain`` — домен из ``helpdesk_mailbox_settings.support_address``;
    если передан и ответ публичный, генерируется канонический ``email_message_id``
    (ТЗ §1.3.3, §5.2) и сохраняется в сообщении для threading.

    При первом публичном ответе без assignee — агент назначает себя
    (ТЗ §4.2.1: «если нет assignee — назначить текущего агента»).

    Внимание (outbox-инвариант, AGENTS.md): функция НЕ делает ``db.commit()`` —
    только ``flush``. Caller обязан поставить outbox-запись (если ответ
    публичный) в той же транзакции и сделать единый ``commit``. Раньше commit
    был здесь, а outbox — отдельным commit в роутере, что нарушало инвариант
    (сбой второго commit терял письмо заявителю при сохранённом ответе)."""
    from app.services.helpdesk.lifecycle import agent_outbound_reply

    now = datetime.now(UTC)
    is_public = payload.visibility == HelpdeskVisibility.public

    email_message_id = (
        _make_outbound_message_id(ticket.number, support_domain)
        if is_public and support_domain
        else None
    )

    message = HelpdeskMessage(
        ticket_id=ticket.id,
        author_user_id=agent.id,
        author_email=agent.email,
        author_name=agent.full_name,
        direction="outbound",
        visibility=payload.visibility,
        body_text=payload.body_text,
        body_html=payload.body_html,
        source="web",
        email_message_id=email_message_id,
    )
    db.add(message)
    await db.flush()  # нужен message.id/email_message_id для вложений и outbox

    if files:
        from app.services.helpdesk.attachments import upload_attachments

        await upload_attachments(db, ticket=ticket, message_id=message.id, files=files, actor=agent)

    if is_public:
        # Публичный ответ → pending (ждём клиента). First public reply без
        # assignee → авто-назначение текущего агента.
        if ticket.assignee_user_id is None:
            ticket.assignee_user_id = agent.id
            ticket.assigned_at = now
        result = agent_outbound_reply(ticket.status)
        ticket.status = result.status

    ticket.last_activity_at = now

    # Без commit — см. docstring (outbox-инвариант). Caller делает единый commit.
    await db.refresh(message)
    await _eager_load_attachments(db, message)
    return message
