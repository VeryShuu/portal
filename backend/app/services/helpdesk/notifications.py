"""Helpdesk in-app notifications (Этап 4).

In-app уведомления через единый паттерн ``create_notification`` + Redis SSE
(см. ``app/services/notifications.py``). Email-часть (outbound через
``email_outbox``) — этап 5 (требует ``helpdesk_mailbox_settings`` и
``support_domain``); здесь только in-app.

Паттерн вызова (по образцу feedback): продюсер вызывается **после** commit
бизнес-операции, сам делает ``db.commit()`` (уведомления — best-effort, в
отдельной транзакции) и аккумулирует ``_publish``-колбэки для SSE после commit.
Получатели-агенты выбираются по ``helpdesk_agents`` JOIN ``users`` (а не по
``User.role``, как в feedback — агенты это отдельный список).
"""

from __future__ import annotations

import html
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import HELPDESK_REOPEN_WINDOW_DAYS
from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskAgent, HelpdeskTicket
from app.models.user import User
from app.services.email_outbox import KIND_GENERIC, enqueue_outbox_email
from app.services.helpdesk.email_template import (
    render_new_ticket_agent_email,
    render_system_email,
)
from app.services.notifications import create_notification

logger = get_logger(__name__)

_BATCH_SIZE = 500


async def _select_agents_to_notify(
    db: AsyncSession, *, exclude_user_id: uuid.UUID | None = None, require_notify_new: bool = True
) -> list[uuid.UUID]:
    """Все helpdesk-агенты (с живым аккаунтом и notify_inapp), опционально с
    ``notify_new=True``. JOIN users — единый источник правды о членстве."""
    conditions = [
        User.deleted_at.is_(None),
        User.notify_inapp.is_(True),
    ]
    if require_notify_new:
        conditions.append(HelpdeskAgent.notify_new.is_(True))
    q = (
        select(HelpdeskAgent.user_id)
        .join(User, User.id == HelpdeskAgent.user_id)
        .where(*conditions)
    )
    if exclude_user_id is not None:
        q = q.where(HelpdeskAgent.user_id != exclude_user_id)
    res = await db.execute(q)
    return list(res.scalars().all())


async def _fan_out(
    db: AsyncSession,
    redis: Redis,
    *,
    user_ids: list[uuid.UUID],
    type_: str,
    title: str,
    body: str | None,
    link: str | None,
) -> int:
    """Создать уведомления для списка получателей и опубликовать в SSE
    после commit (единый транзакционный batch)."""
    sent = 0
    publish_callbacks: list[Callable[[], Coroutine[Any, Any, None]]] = []
    for uid in user_ids:
        publish = await create_notification(
            db, redis, user_id=uid, type=type_, title=title, body=body, link=link
        )
        publish_callbacks.append(publish)
        sent += 1
    await db.commit()
    for publish in publish_callbacks:
        await publish()
    return sent


async def notify_ticket_created(db: AsyncSession, redis: Redis, *, ticket: HelpdeskTicket) -> int:
    """Новая заявка → уведомление всем агентам с ``notify_new=True``."""
    agent_ids = await _select_agents_to_notify(db, require_notify_new=True)
    sent = await _fan_out(
        db,
        redis,
        user_ids=agent_ids,
        type_="helpdesk_ticket_created",
        title=f"Новая заявка #{ticket.ticket_number}",
        body=ticket.subject,
        link=f"/helpdesk/tickets/{ticket.id}",
    )
    if sent:
        logger.info("helpdesk.notify_created_sent", ticket_id=str(ticket.id), sent=sent)
    return sent


async def notify_ticket_assigned(
    db: AsyncSession,
    redis: Redis,
    *,
    ticket: HelpdeskTicket,
    assignee: User,
    actor: User,
) -> int:
    """Взятие в работу / реассайн → инициатор + новый агент + старый агент
    (если был и отличается). Инициатору — in-app с ФИО ответственного."""
    targets: list[uuid.UUID] = []
    if ticket.requester_user_id is not None and ticket.requester_user_id != actor.id:
        targets.append(ticket.requester_user_id)
    if assignee.id != actor.id:
        targets.append(assignee.id)
    # Уведомление инициатору содержит ФИО ответственного (ТЗ §6).
    sent = await _fan_out(
        db,
        redis,
        user_ids=targets,
        type_="helpdesk_ticket_assigned",
        title=f"Заявка #{ticket.ticket_number} взята в работу",
        body=f"Ответственный: {assignee.full_name}.",
        link=f"/helpdesk/my/{ticket.id}",
    )
    return sent


async def notify_agent_reply(
    db: AsyncSession,
    redis: Redis,
    *,
    ticket: HelpdeskTicket,
    body_preview: str,
) -> int:
    """Публичный ответ агента → инициатору (это и есть «ответ»)."""
    targets: list[uuid.UUID] = []
    if ticket.requester_user_id is not None:
        targets.append(ticket.requester_user_id)
    return await _fan_out(
        db,
        redis,
        user_ids=targets,
        type_="helpdesk_agent_reply",
        title=f"Ответ по заявке #{ticket.ticket_number}",
        body=body_preview,
        link=f"/helpdesk/my/{ticket.id}",
    )


async def notify_requester_reply(
    db: AsyncSession,
    redis: Redis,
    *,
    ticket: HelpdeskTicket,
    body_preview: str,
) -> int:
    """Новое сообщение от клиента → текущему assignee (или всем агентам, если
    не назначен)."""
    if ticket.assignee_user_id is not None:
        targets = [ticket.assignee_user_id]
    else:
        targets = await _select_agents_to_notify(db, require_notify_new=False)
    return await _fan_out(
        db,
        redis,
        user_ids=targets,
        type_="helpdesk_requester_reply",
        title=f"Новое сообщение по заявке #{ticket.ticket_number}",
        body=body_preview,
        link=f"/helpdesk/tickets/{ticket.id}",
    )


async def notify_status_changed(
    db: AsyncSession,
    redis: Redis,
    *,
    ticket: HelpdeskTicket,
    new_status: str,
) -> int:
    """Статус → resolved/closed → инициатору (closed — с инфо о reopen-окне)."""
    targets: list[uuid.UUID] = []
    if ticket.requester_user_id is not None:
        targets.append(ticket.requester_user_id)
    body = None
    if new_status == "closed":
        body = f"Ответить и переоткрыть можно в течение {HELPDESK_REOPEN_WINDOW_DAYS} дн."
    return await _fan_out(
        db,
        redis,
        user_ids=targets,
        type_="helpdesk_status_changed",
        title=f"Статус заявки #{ticket.ticket_number}: {new_status}",
        body=body,
        link=f"/helpdesk/my/{ticket.id}",
    )


# ---------------------------------------------------------------------------
# Email-уведомление инициатору о назначении ответственного (ТЗ §6).
# ---------------------------------------------------------------------------


def build_assigned_email_subject(ticket: HelpdeskTicket) -> str:
    """Тема письма о назначении — с тикет-токеном ``[#TKT-{number}]`` в начале.

    Токен в теме — fallback-matching для входящих ответов (ТЗ §1.3.3): ответ
    заявителя на это письмо вернётся в тот же тикет даже если почтовик оборвёт
    ``In-Reply-To``/``References``.
    """
    return f"[#TKT-{ticket.number}] Заявка принята в работу"


def build_assigned_email_bodies(ticket: HelpdeskTicket, assignee: User) -> tuple[str, str]:
    """Тела письма о назначении ``(html, plain)`` в едином helpdesk-шаблоне.

    Внимание: порядок ``(html, plain)`` — как в ``render_system_email``/
    ``render_reply_email`` (HTML первым). Исторически функция возвращала
    ``(plain, html)``, но с переходом на шаблон порядок унифицирован.

    Данные заявителя/темы и ФИО ответственного экранируются внутри
    ``email_template`` через ``html.escape`` (паттерн meetings/news). Шапка
    (№TKT + тема) и футер (автоматическое уведомление) добавляются шаблоном
    ``render_system_email``."""
    assignee_esc = html.escape(assignee.full_name)
    ticket_number = ticket.number

    plain = (
        "Принята в работу.\n"
        f"Ответственный специалист: {assignee.full_name}.\n\n"
        f"Вы можете ответить на это письмо, чтобы добавить сообщение в заявку "
        f"(оставьте «[#TKT-{ticket_number}]» в теме)."
    )

    html_body = (
        "<p>Заявка принята в работу.</p>"
        f"<p>Ответственный специалист: <strong>{assignee_esc}</strong>.</p>"
        '<p style="color:#888;font-size:0.9em;margin-top:16px;">'
        "Вы можете ответить на это письмо, чтобы добавить сообщение в заявку "
        f"(пожалуйста, не удаляйте «[#TKT-{ticket_number}]» из темы)."
        "</p>"
    )
    return render_system_email(
        ticket=ticket,
        body_html=html_body,
        body_text=plain,
    )


def build_created_email_subject(ticket: HelpdeskTicket) -> str:
    """Тема письма «заявка принята в систему» — с тикет-токеном ``[#TKT-{number}]``.

    Токен в теме — fallback-matching для входящих ответов: ответ заявителя на
    это письмо вернётся в тот же тикет даже если почтовик оборвёт
    ``In-Reply-To``/``References``.
    """
    return f"[#TKT-{ticket.number}] Заявка зарегистрирована"


def build_created_email_bodies(ticket: HelpdeskTicket) -> tuple[str, str]:
    """Тела письма «заявка принята в систему» ``(html, plain)`` в едином
    helpdesk-шаблоне.

    Подтверждение приёма заявки: номер, обращение принято, с заявителем
    свяжется специалист поддержки. Инструкция ответить на письмо, чтобы
    дополнить заявку (с токеном ``[#TKT-{number}]`` в теме для threading).

    Данные темы тикета экранируются внутри ``email_template`` через
    ``html.escape``. Шапка (№TKT + тема) и футер добавляются шаблоном
    ``render_system_email``."""
    ticket_number = ticket.number

    plain = (
        "Ваша заявка принята и зарегистрирована в системе технической поддержки.\n"
        f"Присвоен номер: [#TKT-{ticket_number}].\n\n"
        "С вами свяжется специалист поддержки. Вы можете ответить на это письмо, "
        f"чтобы дополнить заявку (оставьте «[#TKT-{ticket_number}]» в теме)."
    )

    html_body = (
        "<p>Ваша заявка принята и зарегистрирована в системе технической "
        "поддержки.</p>"
        f"<p>Присвоен номер: <strong>[#TKT-{ticket_number}]</strong>.</p>"
        "<p>С вами свяжется специалист поддержки.</p>"
        '<p style="color:#888;font-size:0.9em;margin-top:16px;">'
        "Вы можете ответить на это письмо, чтобы дополнить заявку "
        f"(пожалуйста, не удаляйте «[#TKT-{ticket_number}]» из темы)."
        "</p>"
    )
    return render_system_email(
        ticket=ticket,
        body_html=html_body,
        body_text=plain,
    )


# ---------------------------------------------------------------------------
# Email-уведомление агентам о новой заявке (ТЗ: оповещение всех агентов).
# ---------------------------------------------------------------------------


def build_new_ticket_agent_subject(ticket: HelpdeskTicket) -> str:
    """Тема письма-уведомления о новой заявке — с тикет-токеном ``[#TKT-{number}]``.

    Токен в теме — единый паттерн helpdesk-писем. Email отправляется через outbox
    ``kind=generic`` (не входит в email-тред тикета: нет threading-заголовков),
    но токен всё равно полезен агенту для быстрой идентификации заявки в почте.
    """
    return f"[#TKT-{ticket.number}] Новая заявка: {ticket.subject}"


async def _load_agents_for_email(db: AsyncSession) -> list[User]:
    """Все активные helpdesk-агенты, которым слать email о новых заявках.

    Фильтр по двум условиям (симметрично in-app ``_select_agents_to_notify``,
    где проверяется ``notify_inapp``):
    * ``HelpdeskAgent.notify_new=True`` — операционный флаг агента (хочет
      уведомления о новых заявках);
    * ``User.notify_email=True`` — глобальное согласие пользователя на
      email-уведомления.

    JOIN users — единый источник правды о членстве и аккаунте
    (``deleted_at IS NULL``). Не по ``User.role`` (агенты — отдельный список).
    """
    res = await db.execute(
        select(User)
        .join(HelpdeskAgent, HelpdeskAgent.user_id == User.id)
        .where(
            User.deleted_at.is_(None),
            User.notify_email.is_(True),
            HelpdeskAgent.notify_new.is_(True),
        )
    )
    return list(res.scalars().all())


async def notify_ticket_created_email(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    first_message: object,
) -> int:
    """Отправить email-уведомление всем агентам о новой заявке.

    Использует outbox ``kind=generic`` (не ``helpdesk``): уведомление не входит
    в email-тред тикета (нет threading-заголовков ``Message-ID``/``References``),
    не требует настроенного ``helpdesk_mailbox_settings`` (SMTP-настройки общие).
    Это позволяет оповещать агентов даже в web-only режиме helpdesk (без IMAP).

    По образцу ``send_digests`` (``digest.py``): для каждого агента — отдельная
    outbox-запись (персональный ``to_email``), единый ``db.commit`` в конце.
    Тела письма (plain+html) одинаковые для всех (нет персонализации по агенту).

    Контакты заявителя (ФИО/почта/телефон/внутренний номер) берутся из модели
    ``User`` через ``resolve_requester_user`` — единый источник с карточкой
    тикета (``build_requester_profile``). Для гостевой заявки без аккаунта
    (``requester is None``) шаблон берёт снимок имени/email из тикета.

    Best-effort: вызывается из роутера/ingress **после** commit бизнес-операции.
    Сам делает ``db.commit()`` (уведомления — best-effort, в отдельной
    транзакции). Возвращает кол-во поставленных в outbox писем.
    """
    agents = await _load_agents_for_email(db)
    if not agents:
        return 0

    # Резолвим пользователя-заявителя для блока контактов (ФИО/телефоны из
    # модели User, как в карточке тикета). Гость без аккаунта → None → шаблон
    # показывает имя/email из снимка тикета.
    from app.services.helpdesk.tickets import resolve_requester_user

    requester = await resolve_requester_user(db, ticket=ticket)

    # ``first_message`` может быть ORM HelpdeskMessage (с body_html/body_text) —
    # передаём как есть в шаблон (он читает атрибуты через getattr).
    html_body, plain_body = render_new_ticket_agent_email(
        ticket=ticket,
        first_message=first_message,  # type: ignore[arg-type]
        requester=requester,
    )
    subject = build_new_ticket_agent_subject(ticket)

    for agent in agents:
        await enqueue_outbox_email(
            db,
            kind=KIND_GENERIC,
            to_email=agent.email,
            subject=subject,
            body_html=html_body,
            body_text=plain_body,
            related_resource_type="helpdesk_ticket",
            related_resource_id=ticket.id,
            created_by_user_id=agent.id,
        )

    await db.commit()
    sent = len(agents)
    logger.info("helpdesk.notify_created_email_sent", ticket_id=str(ticket.id), sent=sent)
    return sent
