"""Shared schema mappers for the helpdesk API package."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket
from app.models.user import User
from app.schemas.helpdesk import (
    AttachmentOut,
    HelpdeskDirection,
    HelpdeskSource,
    HelpdeskStatus,
    MessageOut,
    ParticipantOut,
    RequesterProfileOut,
    TicketAgentOut,
    TicketListItemOut,
    TicketOut,
)
from app.services.helpdesk.archive import ArchivedTicket

__all__ = [
    "archived_ticket_to_agent_out",
    "archived_ticket_to_list_out",
    "archived_ticket_to_out",
    "build_requester_profile",
    "message_to_out",
    "ticket_to_agent_out",
    "ticket_to_list_out",
    "ticket_to_out",
]


def _attachments(msg: HelpdeskMessage) -> list[AttachmentOut]:
    """Вложения сообщения: сериализуем то, что загружено через ``selectin``
    relationship.

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


def message_to_out(
    msg: HelpdeskMessage, *, include_attachment_warnings: bool = False
) -> MessageOut:
    return MessageOut(
        id=msg.id,
        direction=HelpdeskDirection(msg.direction),
        source=HelpdeskSource(msg.source),
        author_email=msg.author_email,
        author_name=msg.author_name,
        author_user_id=msg.author_user_id,
        body_text=msg.body_text,
        body_html=msg.body_html,
        attachments=_attachments(msg),
        attachment_warnings=(
            list(getattr(msg, "attachment_warnings", None) or [])
            if include_attachment_warnings
            else []
        ),
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


def _archive_datetime(value: object, fallback: datetime) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
        except ValueError:
            pass
    return fallback


def archived_ticket_to_list_out(
    ticket: ArchivedTicket, *, assignee_name: str | None = None
) -> TicketListItemOut:
    return TicketListItemOut(
        id=ticket.id,
        number=ticket.row.number,
        subject=ticket.row.subject,
        status=HelpdeskStatus.closed,
        source=HelpdeskSource(ticket.source),
        requester_email=ticket.row.requester_email,
        requester_user_id=ticket.row.requester_user_id,
        requester_name=ticket.requester_name,
        assignee_user_id=ticket.row.assignee_user_id,
        assignee_name=assignee_name,
        last_activity_at=_archive_datetime(
            _payload_ticket_value(ticket, "last_activity_at"), ticket.row.closed_at
        ),
        created_at=ticket.row.opened_at,
        archived=True,
    )


def _payload_ticket_value(ticket: ArchivedTicket, key: str) -> object:
    payload = ticket.row.payload
    if not isinstance(payload, dict):
        return None
    raw_ticket = payload.get("ticket")
    return raw_ticket.get(key) if isinstance(raw_ticket, dict) else None


def _archived_messages(ticket: ArchivedTicket) -> list[MessageOut]:
    """Map legacy snapshot messages safely.

    Early snapshots do not retain attachment IDs, per-message source, author
    IDs/names, or Cc. We expose the preserved conversation text and never emit
    fake attachment links that could target an unrelated live record.
    """
    result: list[MessageOut] = []
    legacy_attachments = _archive_attachments(ticket)
    for index, raw in enumerate(ticket.messages):
        try:
            message_id = uuid.UUID(str(raw.get("id")))
        except (TypeError, ValueError):
            continue
        direction = raw.get("direction")
        if direction not in {"inbound", "outbound"}:
            continue
        result.append(
            MessageOut(
                id=message_id,
                direction=HelpdeskDirection(direction),
                source=HelpdeskSource(ticket.source),
                author_email=str(raw.get("author_email") or ""),
                author_name=raw.get("author_name")
                if isinstance(raw.get("author_name"), str)
                else None,
                author_user_id=_archive_uuid(raw.get("author_user_id")),
                body_text=str(raw.get("body_text") or ""),
                body_html=raw.get("body_html") if isinstance(raw.get("body_html"), str) else None,
                attachments=_archive_message_attachments(ticket, raw)
                # Old snapshots have no message association; attach the
                # preserved files to the first message so they remain usable.
                or (legacy_attachments if index == 0 else []),
                cc=_archive_cc(raw),
                created_at=_archive_datetime(raw.get("created_at"), ticket.row.opened_at),
            )
        )
    return result


def _archive_uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _archive_attachment_out(ticket: ArchivedTicket, raw: object) -> AttachmentOut | None:
    if not isinstance(raw, dict):
        return None
    filename = raw.get("filename")
    original_name = raw.get("original_name")
    if not isinstance(filename, str) or not isinstance(original_name, str):
        return None
    attachment_id = _archive_uuid(raw.get("id")) or uuid.uuid5(ticket.id, filename)
    return AttachmentOut(
        id=attachment_id,
        filename=filename,
        original_name=original_name,
        content_type=str(raw.get("content_type") or "application/octet-stream"),
        size_bytes=int(raw.get("size_bytes") or 0),
        created_at=_archive_datetime(raw.get("created_at"), ticket.row.closed_at),
        download_url=f"/api/v1/helpdesk/tickets/{ticket.id}/archive-attachments/{filename}",
    )


def _archive_attachments(ticket: ArchivedTicket) -> list[AttachmentOut]:
    payload = ticket.row.payload if isinstance(ticket.row.payload, dict) else {}
    raw = payload.get("attachments_meta", [])
    return (
        [item for value in raw if (item := _archive_attachment_out(ticket, value))]
        if isinstance(raw, list)
        else []
    )


def _archive_message_attachments(ticket: ArchivedTicket, message: dict) -> list[AttachmentOut]:
    raw = message.get("attachments", [])
    return (
        [item for value in raw if (item := _archive_attachment_out(ticket, value))]
        if isinstance(raw, list)
        else []
    )


def _archive_cc(raw: dict) -> list[ParticipantOut]:
    cc = raw.get("cc", [])
    if not isinstance(cc, list):
        return []
    return [
        ParticipantOut(email=item["email"], name=item.get("name"), is_requester=False)
        for item in cc
        if isinstance(item, dict) and isinstance(item.get("email"), str)
    ]


def archived_ticket_to_out(
    ticket: ArchivedTicket,
    *,
    requester_profile: RequesterProfileOut | None = None,
    assignee_name: str | None = None,
) -> TicketOut:
    return TicketOut(
        id=ticket.id,
        number=ticket.row.number,
        subject=ticket.row.subject,
        description=ticket.description,
        description_html=ticket.description_html,
        status=HelpdeskStatus.closed,
        source=HelpdeskSource(ticket.source),
        assignee_name=assignee_name,
        requester_profile=requester_profile,
        messages=_archived_messages(ticket),
        last_activity_at=_archive_datetime(
            _payload_ticket_value(ticket, "last_activity_at"), ticket.row.closed_at
        ),
        created_at=ticket.row.opened_at,
        archived=True,
    )


def archived_ticket_to_agent_out(
    ticket: ArchivedTicket,
    *,
    requester_profile: RequesterProfileOut | None = None,
    assignee_name: str | None = None,
) -> TicketAgentOut:
    base = archived_ticket_to_out(
        ticket, requester_profile=requester_profile, assignee_name=assignee_name
    )
    participants = _archived_participants(ticket)
    return TicketAgentOut(
        **base.model_dump(),
        requester_user_id=ticket.row.requester_user_id,
        requester_email=ticket.row.requester_email,
        requester_name=ticket.requester_name,
        assignee_user_id=ticket.row.assignee_user_id,
        assigned_at=None,
        closed_at=ticket.row.closed_at,
        closed_by_user_id=ticket.row.closed_by_user_id,
        references_archived_ticket_number=None,
        participants=participants,
    )


def _archived_participants(ticket: ArchivedTicket) -> list[ParticipantOut]:
    result = [
        ParticipantOut(
            email=ticket.row.requester_email,
            name=ticket.requester_name,
            is_requester=True,
        )
    ]
    seen = {ticket.row.requester_email.lower()}
    for message in ticket.messages:
        email = message.get("author_email")
        if isinstance(email, str) and email and email.lower() not in seen:
            seen.add(email.lower())
            result.append(ParticipantOut(email=email, name=None, is_requester=False))
    return result


def ticket_to_out(
    ticket: HelpdeskTicket,
    *,
    requester_profile: RequesterProfileOut | None = None,
) -> TicketOut:
    """Карточка тикета."""
    messages = list(ticket.messages)
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
    """Карточка для агентов/админов: служебные поля (assignee, closed_at,
    archived-reference)."""
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
        messages=[message_to_out(m, include_attachment_warnings=True) for m in ticket.messages],
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
