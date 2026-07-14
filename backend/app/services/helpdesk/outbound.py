"""Исходящие email-продюсеры для helpdesk (outbox, ``kind=helpdesk``).

Вынесено из ``app/api/helpdesk/tickets.py`` (AGENTS.md: «бизнес-логика в
``app/services/``, не в API-роутах»). Роутер остаётся тонким wiring-слоем.

Outbox-инвариант (AGENTS.md → Email outbox-pattern): функции НЕ делают
``db.commit()`` — только добавляют ``email_outbox``-строку в текущую транзакцию.
Caller (роутер) обязан сделать единый ``commit`` вместе с бизнес-операцией
(ответом агента / назначением). Раньше commit был раздельным → сбой между
ними терял письмо заявителю при сохранённой бизнес-операции.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.helpdesk import (
    HelpdeskAttachment,
    HelpdeskMailboxSettings,
    HelpdeskMessage,
    HelpdeskTicket,
)
from app.models.user import User
from app.services.email_outbox import KIND_HELPDESK, enqueue_outbox_email
from app.services.helpdesk.email_template import render_reply_email
from app.services.helpdesk.email_thread import build_thread_history
from app.services.helpdesk.notifications import (
    build_assigned_email_bodies,
    build_assigned_email_subject,
)


def _sanitize_header_field(value: str | None) -> str:
    """Убрать CR/LF из значения, попадающего в email-заголовок (H-4).

    Defense-in-depth: outbox worker уже стрипает CRLF в ``_sanitize_header``
    (фикс E3), но продюсер тоже должен санировать — на случай нового
    продюсера, минующего worker, или изменения outbox-контракта. Источник
    ``ticket.subject``/``requester_email`` — attacker-controlled (входящий
    email с произвольным From/Subject). Без стрипа ``Subject: ...\\r\\nBcc:``
    инжектит BCC-заголовок (фишинг с доверенного support-адреса).
    """
    if not value:
        return ""
    return value.replace("\r", " ").replace("\n", " ").strip()


def support_domain(mailbox: HelpdeskMailboxSettings | None) -> str | None:
    """Домен из ``support_address`` (часть после ``@``). None, если пуст/невалиден."""
    if mailbox is None:
        return None
    addr = (mailbox.support_address or "").strip()
    if "@" not in addr:
        return None
    domain = addr.split("@", 1)[1].strip()
    return domain or None


async def load_mailbox(db: AsyncSession) -> HelpdeskMailboxSettings | None:
    """Singleton ``helpdesk_mailbox_settings`` (id=1) или None, если не настроен."""
    res = await db.execute(select(HelpdeskMailboxSettings).where(HelpdeskMailboxSettings.id == 1))
    return res.scalars().one_or_none()


async def load_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalars().one_or_none()


async def collect_ticket_references(
    db: AsyncSession, *, ticket_id: uuid.UUID, exclude_message_id: uuid.UUID | None = None
) -> list[str]:
    """Цепочка ``email_message_id`` предшествующих сообщений тикета (для
    ``In-Reply-To``/``References``). Опционально исключает свежее сообщение."""
    q = select(HelpdeskMessage.email_message_id).where(
        HelpdeskMessage.ticket_id == ticket_id,
        HelpdeskMessage.email_message_id.is_not(None),
    )
    if exclude_message_id is not None:
        q = q.where(HelpdeskMessage.id != exclude_message_id)
    q = q.order_by(HelpdeskMessage.created_at)
    res = await db.execute(q)
    return [r for r in res.scalars().all() if r]


async def enqueue_reply_outbound(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    mailbox: HelpdeskMailboxSettings,
) -> None:
    """Собрать payload и поставить исходящее письмо-ответ в outbox.

    Содержимое файлов НЕ кладётся в payload — только метаданные (§5.2).

    Письмо несёт историю переписки **под** reply-маркером (промышленный стандарт
    helpdesk — Zammad/Freshdesk): заявитель видит контекст в почте, а при ответе
    его почтовый клиент цитирует весь блок, и ``strip_quoted_reply`` (email_quote)
    режет строго по ``REPLY_MARKER_TOKEN`` → в ленте портала остаётся только
    чистый ответ.

    Без ``commit`` — outbox-запись коммитится единым commit'ом вместе с ответом
    агента в роутере (outbox-инвариант AGENTS.md).
    """
    references = await collect_ticket_references(
        db, ticket_id=ticket.id, exclude_message_id=message.id
    )

    atts_res = await db.execute(
        select(HelpdeskAttachment).where(HelpdeskAttachment.message_id == message.id)
    )
    attachments_meta = [
        {
            "filename": a.filename,
            "original_name": a.original_name,
            "content_type": a.content_type,
        }
        for a in atts_res.scalars().all()
    ]

    domain = support_domain(mailbox)
    # ``assignee_user_id`` — для подписи «Исполнитель» в блоках таймлайна (если
    # автор сообщения = назначенный специалист тикета). Сравнение UUID в шаблоне,
    # без доп. запросов. В шапке исполнитель больше не выводится (убрано).
    assignee_user_id = getattr(ticket, "assignee_user_id", None)
    # История предшествующих публичных сообщений (internal-заметки не входят).
    # ``ticket.messages`` подгружен через selectinload в ``fetch_ticket_for_agent``
    # на момент вызова из ``add_agent_message`` (до создания нового сообщения);
    # ``exclude_id`` — страховка на случай, если новый ответ уже в коллекции.
    # ``assignee_user_id`` — для подписи «Исполнитель» в блоках истории.
    history_plain, history_html = build_thread_history(
        list(ticket.messages),
        exclude_id=message.id,
        ticket_number=ticket.number,
        assignee_user_id=assignee_user_id,
    )
    # Единый шаблон: шапка + ответ агента + reply-маркер (точка отсечения цитаты
    # при ответе заявителя, см. ``email_quote``) + история + футер. Маркер и
    # история добавляются шаблоном ТОЛЬКО в outbox-копии тела — сохранённое в БД
    # ``HelpdeskMessage`` не мутируется (агент в ленте портала видит чистый ответ).
    #
    # H-6: если агент отправил только plain-text (body_html пуст), экранируем
    # body_text через _esc перед обёрткой в <pre> — иначе ``</pre><script>...``
    # в тексте агента инжектит HTML (источник — доверенный внутренний агент, но
    # несоответствие с _message_body_html, который всегда экранирует).
    from app.services.helpdesk.email_template import _esc

    agent_body_html = message.body_html or f"<pre>{_esc(message.body_text)}</pre>"
    body_html, body_text = render_reply_email(
        ticket=ticket,
        agent_body_html=agent_body_html,
        agent_body_text=message.body_text,
        history_html=history_html,
        history_plain=history_plain,
        message_author=message.author_name or message.author_email or "",
        message_created_at=message.created_at,
        message_attachments=list(getattr(message, "attachments", None) or []),
        assignee_user_id=assignee_user_id,
        message_author_user_id=message.author_user_id,
    )
    await enqueue_outbox_email(
        db,
        kind=KIND_HELPDESK,
        to_email=_sanitize_header_field(ticket.requester_email),
        subject=_sanitize_header_field(f"[#TKT-{ticket.number}] {ticket.subject}"),
        body_html=body_html,
        body_text=body_text,
        payload={
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.number,
            "message_id_header": message.email_message_id,
            "in_reply_to": references[-1] if references else None,
            "references": references,
            "reply_to": mailbox.support_address,
            "subject_original": _sanitize_header_field(ticket.subject),
            "support_domain": domain,
            "support_address": mailbox.support_address,
            "attachments": attachments_meta,
        },
        related_resource_type="helpdesk_ticket",
        related_resource_id=ticket.id,
        created_by_user_id=message.author_user_id,
    )


async def enqueue_assigned_email(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    assignee: User,
    actor: User,
    mailbox: HelpdeskMailboxSettings,
) -> None:
    """Email-уведомление инициатору о назначении ответственного (ТЗ §6).

    Только при сконфигурированном mailbox (есть ``support_domain`` — проверяет
    caller). Письмо входит в email-тред тикета — токен ``[#TKT-{number}]`` в
    теме и ``References`` обеспечивают, что ответ заявителя вернётся в тикет
    даже без живого ``In-Reply-To``. ``Message-ID`` генерируется из свежего uuid
    (это системное письмо, не ``helpdesk_messages``), но в формате треда
    (``tkn-{number}-{uuid}@domain``), чтобы ответ попал в ``references``.

    Без ``commit`` — единый commit в роутере вместе с назначением
    (outbox-инвариант AGENTS.md).
    """
    domain = support_domain(mailbox)
    references = await collect_ticket_references(db, ticket_id=ticket.id)

    # Генерируем Message-ID в каноническом формате треда тикета. Используется
    # свежий uuid (это уведомление, не HelpdeskMessage), но он валиден как
    # ``References``-ancestor для будущих ответов.
    message_uuid = uuid.uuid4()
    message_id_header = f"<tkn-{ticket.number}-{message_uuid}@{domain}>"

    html_body, plain = build_assigned_email_bodies(ticket, assignee)
    await enqueue_outbox_email(
        db,
        kind=KIND_HELPDESK,
        to_email=_sanitize_header_field(ticket.requester_email),
        subject=_sanitize_header_field(build_assigned_email_subject(ticket)),
        body_html=html_body,
        body_text=plain,
        payload={
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.number,
            "message_id_header": message_id_header,
            "in_reply_to": references[-1] if references else None,
            "references": references,
            "reply_to": mailbox.support_address,
            "subject_original": _sanitize_header_field(ticket.subject),
            "support_domain": domain,
            "support_address": mailbox.support_address,
            "attachments": [],
        },
        related_resource_type="helpdesk_ticket",
        related_resource_id=ticket.id,
        created_by_user_id=actor.id,
    )
