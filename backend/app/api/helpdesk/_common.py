"""Shared schema mappers for the helpdesk API package.

Сериализаторы отделяют «публичное» представление (для инициатора — без
``internal``-сообщений) от служебных полей. Здесь же — принципиальный
ACL-фильтр: сообщения c ``visibility='internal'`` никогда не попадают в
ответ инициатору (ТЗ §3.2, §4.5), даже если по какой-то причине оказались в
загруженной коллекции.
"""

from __future__ import annotations

import uuid

from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket
from app.models.user import User
from app.schemas.helpdesk import (
    AttachmentOut,
    HelpdeskDirection,
    HelpdeskSource,
    HelpdeskStatus,
    HelpdeskVisibility,
    MessageOut,
    ParticipantOut,
    RequesterProfileOut,
    TicketAgentOut,
    TicketListItemOut,
    TicketOut,
)

__all__ = [
    "build_requester_profile",
    "message_to_out",
    "ticket_to_agent_out",
    "ticket_to_list_out",
    "ticket_to_out",
]


def _public_messages(messages: list[HelpdeskMessage]) -> list[HelpdeskMessage]:
    """Только публичные сообщения (ACL-фильтр для инициатора)."""
    return [m for m in messages if m.visibility != HelpdeskVisibility.internal.value]


def _attachments(msg: HelpdeskMessage) -> list[AttachmentOut]:
    """Вложения сообщения. ``internal``-сообщения для инициатора уже
    отфильтрованы выше (``_public_messages``), поэтому здесь просто
    сериализуем то, что загружено через ``selectin`` relationship.

    **Inline-картинки исключаются** (``is_inline=True``): они сохранены в БД
    как attachment (для ACL/скачивания), но в теле сообщения уже рендерятся
    по ``<img src="/api/v1/helpdesk/attachments/{id}">`` — показывать их ещё
    и ссылками-вложениями внизу пузыря было бы дублированием. См.
    ``email_images._localize_cid``/``_localize_remote``.
    """
    return [
        AttachmentOut.model_validate(a)
        for a in (getattr(msg, "attachments", []) or [])
        if not getattr(a, "is_inline", False)
    ]


def _cc_participants(msg: HelpdeskMessage) -> list[ParticipantOut]:
    """Cc конкретного сообщения → ``[ParticipantOut]`` (миграция 083).

    ``msg.cc`` — JSONB ``[{"email","name"}]`` или ``None`` (старые сообщения,
    ответы без копии). Нормализуем в список схем; ``is_requester`` всегда
    ``False`` — requester определяется на уровне тикета, не сообщения.
    """
    raw = getattr(msg, "cc", None) or []
    if not isinstance(raw, list):
        return []
    out: list[ParticipantOut] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        email = p.get("email")
        if not email or not isinstance(email, str):
            continue
        name = p.get("name")
        out.append(
            ParticipantOut(
                email=email,
                name=name if isinstance(name, str) and name else None,
                is_requester=False,
            )
        )
    return out


def message_to_out(msg: HelpdeskMessage) -> MessageOut:
    return MessageOut(
        id=msg.id,
        direction=HelpdeskDirection(msg.direction),
        visibility=HelpdeskVisibility(msg.visibility),
        source=HelpdeskSource(msg.source),
        author_email=msg.author_email,
        author_name=msg.author_name,
        author_user_id=msg.author_user_id,
        body_text=msg.body_text,
        body_html=msg.body_html,
        attachments=_attachments(msg),
        cc=_cc_participants(msg),
        created_at=msg.created_at,
    )


def _assignee_name(ticket: HelpdeskTicket) -> str | None:
    return ticket.assignee.full_name if ticket.assignee is not None else None


def _requester_display_name(ticket: HelpdeskTicket) -> str | None:
    """Отображаемое имя заявителя для списков.

    ``requester_name`` — снимок имени на момент создания тикета. Для веб-заявок
    он всегда заполнен (``user.full_name``), а для email-заявок зависит от
    оформления заголовка ``From`` отправителем: голый ``user@host`` без
    display-name → ``requester_name IS NULL`` → в списке отображался бы email,
    хотя аккаунт заявителя известен (``requester_user_id`` ссылается на
    сотрудника). Чтобы список был единообразен с карточкой (где профиль строится
    из живой модели ``User``), при пустом снимке берём ``full_name`` из
    привязанного пользователя. Гость без аккаунта (``requester_user`` is None)
    → ``None`` → фронт показывает ``requester_email``.
    """
    if ticket.requester_name:
        return ticket.requester_name
    if ticket.requester_user is not None:
        return ticket.requester_user.full_name
    return None


def _attr_str(attributes: object, key: str) -> str | None:
    """Строковое значение из JSONB-``attributes`` пользователя (с type-гардом).

    ``city`` и ``mobile`` хранятся в ``users.attributes`` как строки (см.
    ``StaffCard.vue``/``staff_xlsx.py``). Любой не-строковый тип (число, null)
    игнорируется — берём только осмысленные строковые значения.
    """
    if not isinstance(attributes, dict):
        return None
    value = attributes.get(key)
    return value if isinstance(value, str) and value else None


def build_requester_profile(user: User | None) -> RequesterProfileOut | None:
    """Собрать краткий профиль заявителя из модели ``User``.

    Возвращает ``None``, если пользователь не передан (гостевая заявка без
    совпадения по email) — в этом случае блок профиля не отрисовывается.
    Поля ``city``/``mobile_phone`` берутся из JSONB ``attributes`` (ключи
    ``city``/``mobile``), ``internal_phone`` — из нативной колонки ``phone``.
    """
    if user is None:
        return None
    attrs = user.attributes or {}
    return RequesterProfileOut(
        email=user.email,
        full_name=user.full_name,
        department=user.department,
        position=user.position,
        city=_attr_str(attrs, "city"),
        mobile_phone=_attr_str(attrs, "mobile"),
        internal_phone=user.phone or None,
    )


def ticket_to_list_out(ticket: HelpdeskTicket, *, unread: bool | None = None) -> TicketListItemOut:
    return TicketListItemOut(
        id=ticket.id,
        number=ticket.number,
        subject=ticket.subject,
        status=HelpdeskStatus(ticket.status),
        source=HelpdeskSource(ticket.source),
        requester_email=ticket.requester_email,
        requester_user_id=ticket.requester_user_id,
        # Резолвим имя: снимок requester_name → full_name привязанного
        # пользователя → None (гость, фронт покажет email). См. _requester_display_name.
        requester_name=_requester_display_name(ticket),
        assignee_user_id=ticket.assignee_user_id,
        assignee_name=_assignee_name(ticket),
        last_activity_at=ticket.last_activity_at,
        created_at=ticket.created_at,
        # Unread-state: ``None`` по умолчанию (для списков, где он не считается
        # — например ``/tickets/my`` у заявителя). Сериализатор только передаёт
        # то, что посчитал роутер через ``enrich_with_unread`` — сама логика
        # «новее last_seen_at» живёт в сервисе.
        unread=unread,
    )


def ticket_to_out(
    ticket: HelpdeskTicket,
    *,
    requester_view: bool = True,
    requester_profile: RequesterProfileOut | None = None,
) -> TicketOut:
    """Карточка тикета. При ``requester_view=True`` (по умолчанию) internal-сообщения
    отсекаются — это безопасный путь инициатора."""
    messages = _public_messages(ticket.messages) if requester_view else list(ticket.messages)
    return TicketOut(
        id=ticket.id,
        number=ticket.number,
        subject=ticket.subject,
        description=ticket.description,
        description_html=ticket.description_html,
        status=HelpdeskStatus(ticket.status),
        source=HelpdeskSource(ticket.source),
        assignee_name=_assignee_name(ticket),
        requester_profile=requester_profile,
        messages=[message_to_out(m) for m in messages],
        last_activity_at=ticket.last_activity_at,
        created_at=ticket.created_at,
    )


def _is_owned_by(ticket: HelpdeskTicket | None, user_id: uuid.UUID) -> bool:
    return ticket is not None and ticket.requester_user_id == user_id


def _collect_participants(
    ticket: HelpdeskTicket, *, requester_email: str | None
) -> list[ParticipantOut]:
    """Все участники тикета «в сборе» (миграция 083).

    Агрегация одним проходом по сообщениям: ``requester_email`` (всегда первый,
    помечен ``is_requester=True``) ∪ Cc всех сообщений ∪ ``author_email`` всех
    сообщений (на случай, если заявитель ответил с другого адреса, или в тред
    включился третий участник через «ответить всем» извне). Дедупликация — по
    lowercased email.

    Не хранится в БД (денормализация вредна: Cc-состав меняется, stale-данные
    привели бы к «ответили не тем»). Источник для блока «Участники» в карточке
    агента и для pre-fill чекбокса «Ответить всем».
    """
    participants: list[ParticipantOut] = []
    seen: set[str] = set()
    requester_lc = (requester_email or "").strip().lower()

    def _add(email: str, name: str | None, *, is_requester: bool) -> None:
        key = email.strip().lower()
        if not key or "@" not in key or key in seen:
            return
        seen.add(key)
        participants.append(
            ParticipantOut(
                email=key,
                name=(name.strip() if isinstance(name, str) and name.strip() else None),
                is_requester=is_requester,
            )
        )

    # Requester — всегда первым (канонический «To» треда).
    if requester_lc:
        _add(requester_email or "", ticket.requester_name, is_requester=True)

    for m in ticket.messages:
        _add(m.author_email, m.author_name, is_requester=False)
        raw_cc = getattr(m, "cc", None) or []
        if isinstance(raw_cc, list):
            for p in raw_cc:
                if isinstance(p, dict) and isinstance(p.get("email"), str):
                    raw_name = p.get("name")
                    _add(
                        p["email"],
                        raw_name if isinstance(raw_name, str) else None,
                        is_requester=False,
                    )

    return participants


def ticket_to_agent_out(
    ticket: HelpdeskTicket,
    *,
    requester_profile: RequesterProfileOut | None = None,
) -> TicketAgentOut:
    """Карточка для агентов/админов: видны все сообщения (включая internal)
    и служебные поля."""
    return TicketAgentOut(
        id=ticket.id,
        number=ticket.number,
        subject=ticket.subject,
        description=ticket.description,
        description_html=ticket.description_html,
        status=HelpdeskStatus(ticket.status),
        source=HelpdeskSource(ticket.source),
        assignee_name=_assignee_name(ticket),
        requester_profile=requester_profile,
        messages=[message_to_out(m) for m in ticket.messages],
        requester_user_id=ticket.requester_user_id,
        requester_email=ticket.requester_email,
        requester_name=ticket.requester_name,
        assignee_user_id=ticket.assignee_user_id,
        assigned_at=ticket.assigned_at,
        closed_at=ticket.closed_at,
        closed_by_user_id=ticket.closed_by_user_id,
        references_archived_ticket_number=ticket.references_archived_ticket_number,
        participants=_collect_participants(ticket, requester_email=ticket.requester_email),
        last_activity_at=ticket.last_activity_at,
        created_at=ticket.created_at,
    )
