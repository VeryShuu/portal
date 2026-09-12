"""IMAP ingress for helpdesk (ТЗ §1.3, §5.1, §5.3).

Воркер ``poll_helpdesk_mailbox`` ходит на support-mailbox, забирает все письма
папки (``SEARCH ALL`` — включая прочитанные, т.к. оператор читает ящик вручную;
дедупликация по ``helpdesk_email_log``), парсит и сопоставляет с тикетами.
Идемпотентность — через ``helpdesk_email_log`` (по ``Message-ID`` или
synthetic id). Anti-loop — по заголовкам ``Auto-Submitted`` / ``Precedence`` и
совпадению ``From`` с ``support_address`` (ТЗ §5.3).

Архитектурные решения (ТЗ §1.3):
* Dynamic interval — cron статически раз в 30 c, реальный
  ``poll_interval_seconds`` применяется внутри через Redis
  ``helpdesk:imap:last_poll_at``.
* Distributed lock ``helpdesk:imap:poll_lock`` (TTL 5 мин).
* Письма без ``Message-ID`` → synthetic id.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from email import message_from_bytes
from email.message import Message
from email.utils import getaddresses
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.sanitize import sanitize_email_html_for_localization, sanitize_html
from app.models.helpdesk import (
    HelpdeskEmailLog,
    HelpdeskMailboxSettings,
    HelpdeskMessage,
    HelpdeskTicket,
)
from app.models.user import User
from app.schemas.helpdesk import HelpdeskDirection, HelpdeskSource, HelpdeskStatus
from app.services.helpdesk import ingress_imap
from app.services.helpdesk import threading as threading_utils
from app.services.helpdesk.attachments import cleanup_recorded_files
from app.services.helpdesk.email_quote import html_to_plain, strip_quoted_html, strip_quoted_reply
from app.services.helpdesk.email_signature import strip_email_signature, strip_plain_signature
from app.services.helpdesk.lifecycle import (
    REQUESTER_REOPEN_STATUSES,
    requester_reply,
    requester_reply_on_closed,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from app.services.helpdesk.attachments import _TotalTracker

logger = get_logger(__name__)

# Compatibility aliases keep existing production imports and test patch paths
# stable while the IMAP protocol boundary lives in ``ingress_imap``.
_extract_rfc822 = ingress_imap._extract_rfc822
_make_imap_client = ingress_imap._make_imap_client
_make_imap_client_raw = ingress_imap._make_imap_client_raw
_safe_delete = ingress_imap._safe_delete
_safe_seen = ingress_imap._safe_seen
_search_all = ingress_imap._search_all
probe_imap_connection = ingress_imap.probe_imap_connection

LAST_POLL_KEY = "helpdesk:imap:last_poll_at"
POLL_LOCK_KEY = "helpdesk:imap:poll_lock"
POLL_LOCK_TTL = 300  # 5 минут

# ── Anti-loop detection (ТЗ §5.3) ────────────────────────────────────────────

_AUTO_SUBMITTED_VALUES = ("auto-replied", "auto-generated", "auto-notified")
_PRECEDENCE_BULK = ("bulk", "list", "junk")


def is_auto_reply(msg: Message) -> bool:
    """Признаки авто-ответа / bulk-письма → не создавать тикет (anti-loop)."""
    auto_sub = (msg.get("Auto-Submitted") or "").strip().lower()
    if auto_sub and any(v in auto_sub for v in _AUTO_SUBMITTED_VALUES):
        return True
    precedence = (msg.get("Precedence") or "").strip().lower()
    if precedence in _PRECEDENCE_BULK:
        return True
    return bool(msg.get("X-Auto-Response-Suppress"))


def is_from_self(msg: Message, support_address: str) -> bool:
    """``From`` совпадает с ``support_address`` → петля (наш собственный
    bounce/auto-reply), не обрабатываем."""
    from_addrs = [a.lower() for _n, a in getaddresses(msg.get_all("From", []))]
    return support_address.lower() in from_addrs


# ── Mailbox polling ──────────────────────────────────────────────────────────


async def poll_mailbox(
    db: AsyncSession,
    redis: Redis,
    *,
    settings_row: HelpdeskMailboxSettings,
) -> dict:
    """Главная точка входа для cron ``poll_helpdesk_mailbox``.

    Возвращает summary: ``{fetched, created, appended, skipped, errors}``.
    Caller отвечает за открытие ``db`` и чтение ``settings_row`` (а также за
    interval guard и distributed lock — см. ``worker/tasks/helpdesk.py``).
    """
    summary = {"fetched": 0, "created": 0, "appended": 0, "skipped": 0, "errors": 0}
    password = _decrypt_password(settings_row)
    if password is None:
        logger.error("helpdesk.ingress.password_missing")
        summary["errors"] = -1
        return summary

    client = _make_imap_client(settings_row)
    try:
        await asyncio.wait_for(client.wait_hello_from_server(), timeout=15)
        await asyncio.wait_for(client.login(settings_row.imap_username, password), timeout=15)
        await client.select(settings_row.imap_folder)
        # Забираем ВСЕ письма папки, а не только UNSEEN: оператор сам читает
        # ящик (в т.ч. в почтовом клиенте), и ``\Seen``-письма иначе выпадали бы
        # из потока. Дедупликация — по ``helpdesk_email_log`` (Message-ID или
        # synthetic id), так что повторной обработки уже виденных писем не будет.
        uids = await _search_all(client)
        for uid in uids:
            summary["fetched"] += 1
            try:
                await _process_uid(
                    db, redis, client, uid, settings_row=settings_row, summary=summary
                )
            except Exception as exc:
                summary["errors"] += 1
                logger.exception("helpdesk.ingress.uid_failed", uid=uid, error=str(exc))
                # Session poisoning: IntegrityError переводит AsyncSession в
                # failed-state → все последующие UID падают с
                # PendingRollbackError. Явный rollback сбрасывает состояние,
                # один битый UID не роняет весь батч.
                # Audit [H8]: debug-лог на случай если сам rollback упадёт
                # (маскировать оригинальную ошибку не хотим, но диагностика
                # «rollback тоже сломался» ценна).
                try:
                    await db.rollback()
                except Exception:
                    logger.debug("helpdesk.ingress.rollback_failed", exc_info=True)
                # Помечаем прочитанным, но не удаляем — оставляем для разбора.
                # (Фильтр по \Seen больше не используется, но сохраняем флаг для
                # совместимости с почтовыми клиентами оператора.)
                await _safe_seen(client, uid)
        # Физически удалить письма, помеченные \Deleted через _safe_delete
        # (работает только при settings_row.delete_after_fetch). Без EXPUNGE
        # STORE +FLAGS \Deleted лишь вешает флаг, но письмо остаётся в папке.
        if settings_row.delete_after_fetch and uids:
            # Audit [H8]: expunge best-effort — если упадёт, письма останутся
            # с \Deleted-флагом (не критично, оператор дочистит), но debug-лог
            # даёт диагностику почему физическое удаление не состоялось.
            try:
                await client.expunge()
            except Exception:
                logger.debug("helpdesk.ingress.expunge_failed", exc_info=True)
    finally:
        # Logout в finally — обязателен даже при ошибке выше. Audit [H8]:
        # warning-уровень, потому что неудачный logout оставляет IMAP-сессию
        # висеть на сервере (пока не истечёт idle-timeout сервера), что
        # съедает connection-slot и может блокировать другие poll'ы.
        try:
            await client.logout()
        except Exception:
            logger.warning("helpdesk.ingress.logout_failed", exc_info=True)

    # Пустой poll (нет писем, нет ошибок) — это норма: ящик опрашивается каждую
    # минуту, и подавляющее большинство poll'ов пустые. Логирование каждого на
    # INFO генерирует килограммы бесполезного шума в prod (~95% worker-логов от
    # helpdesk). Опускаем такие до DEBUG; INFO остаётся когда есть реальные
    # события (fetched/created/...) или ошибки.
    if summary["fetched"] == 0 and summary["errors"] == 0:
        logger.debug("helpdesk.ingress.poll_done", **summary)
    else:
        logger.info("helpdesk.ingress.poll_done", **summary)
    return summary


def _decrypt_password(row: HelpdeskMailboxSettings) -> str | None:
    try:
        from app.core.secret_crypto import decrypt_secret

        return decrypt_secret(row.imap_password_enc)
    except Exception:
        logger.exception("helpdesk.ingress.password_decrypt_failed")
        return None


async def _process_uid(
    db: AsyncSession,
    redis: Redis,
    client: Any,
    uid: str,
    *,
    settings_row: HelpdeskMailboxSettings,
    summary: dict,
) -> None:
    typ, data = await client.fetch(uid, "(RFC822)")
    if typ != "OK" or not data or not data[0]:
        summary["errors"] += 1
        return
    raw_bytes = _extract_rfc822(data)
    if raw_bytes is None:
        summary["errors"] += 1
        return
    msg = message_from_bytes(raw_bytes)

    message_id = threading_utils.extract_message_id(msg)
    if not message_id:
        message_id = _synthetic_id(msg, uid, settings_row.imap_folder, len(raw_bytes))

    # Идемпотентность: уже видели это письмо?
    existing = await _fetch_log(db, message_id)
    if existing is not None:
        summary["skipped"] += 1
        await _safe_seen(client, uid)
        if settings_row.delete_after_fetch:
            await _safe_delete(client, uid)
        return

    # Anti-loop.
    if is_auto_reply(msg) or is_from_self(msg, settings_row.support_address):
        await _write_log(db, message_id, None, None, status="skipped", error=None)
        summary["skipped"] += 1
        await _safe_seen(client, uid)
        if settings_row.delete_after_fetch:
            await _safe_delete(client, uid)
        return

    await _ingest_message(db, redis, msg, message_id, settings_row, summary)
    await _safe_seen(client, uid)
    if settings_row.delete_after_fetch:
        await _safe_delete(client, uid)


def _synthetic_id(msg: Message, uid: str, mailbox: str, size: int) -> str:
    return threading_utils.synthetic_message_id(
        mailbox=mailbox,
        uid=uid,
        date=msg.get("Date") or "",
        sender=msg.get("From") or "",
        subject=msg.get("Subject") or "",
        size=size,
    )


# ── Matching + ingest ────────────────────────────────────────────────────────


async def _localize_attachments_and_images(
    db: AsyncSession,
    *,
    msg: Message,
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    body_html: str | None,
    include_remote: bool = True,
    attachment_warnings: list[str] | None = None,
) -> tuple[str | None, _TotalTracker]:
    """Локализовать картинки письма (inline cid: + внешние http(s)://) и
    сохранить обычные attach-части как ``HelpdeskAttachment``.

    Возвращает кортеж ``(обновлённый body_html, total_tracker)``. ``body_html``
    — с переписанными src или исходный, если html пуст или ничего не
    локализовано. ``total_tracker`` — зарегистрированные пути файлов для
    cleanup при rollback (H-5). Best-effort: ошибка одной картинки/вложения не
    роняет ingest (см. ``email_images.localize_images``,
    ``attachments.save_image_bytes``).

    При ``include_remote=False`` внешние ``http(s)://`` картинки **не**
    локализуются здесь — это часть рефакторинга H-2: медленный remote-fetch
    вынесен из DB-транзакции в post-commit шаг ``_localize_remote_post_commit``,
    чтобы письмо с множеством картинок не держало DB-соединение открытым
    минутами (pool exhaustion).
    """
    from app.services.helpdesk.attachments import _TotalTracker, save_image_bytes
    from app.services.helpdesk.email_images import extract_inline_parts, localize_images

    total_tracker = _TotalTracker()
    inline_map = extract_inline_parts(msg)

    # Вложения сохраняются из исходного MIME независимо от очистки тела.
    # message/rfc822 сохраняем целиком как .eml и не flatten'им: так первая
    # заявка не теряет пересланную переписку и её внутренние файлы.
    for part in _iter_attachment_parts(msg):
        payload = _attachment_payload(part)
        if not payload:
            continue
        # Имя файла декодируем из RFC 2047 encoded-words (=?UTF-8?B?...?=), иначе
        # original_name сохранится нечитаемым (Subject/From уже декодируются
        # выше через decode_mime_header — тот же механизм).
        is_forwarded_email = part.get_content_type() in {"message/rfc822", "message/global"}
        raw_name = part.get_filename() or ("forwarded.eml" if is_forwarded_email else "attachment")
        original = threading_utils.decode_mime_header(raw_name) or "attachment"
        await save_image_bytes(
            db,
            ticket=ticket,
            message_id=message.id,
            data=payload,
            original_name=original,
            total_tracker=total_tracker,
            declared_content_type=part.get_content_type(),
            rejection_sink=attachment_warnings,
        )

    updated = await localize_images(
        db,
        ticket=ticket,
        message=message,
        html=body_html or "",
        inline_map=inline_map,
        total_tracker=total_tracker,
        include_remote=include_remote,
    )
    return (None if body_html is None else updated), total_tracker


def _iter_attachment_parts(msg: Message) -> list[Message]:
    """Return top-level file parts without descending into attached emails."""

    found: list[Message] = []

    def visit(part: Message, *, root: bool = False) -> None:
        disposition = (part.get_content_disposition() or "").lower()
        is_forwarded_email = part.get_content_type() in {"message/rfc822", "message/global"}
        if not root and (disposition == "attachment" or is_forwarded_email):
            found.append(part)
            return
        if not part.is_multipart():
            return
        payload = part.get_payload()
        if isinstance(payload, list):
            for child in payload:
                if isinstance(child, Message):
                    visit(child)

    visit(msg, root=True)
    return found


def _attachment_payload(part: Message) -> bytes | None:
    """Decode a regular part or serialize an attached email as an ``.eml``."""

    if part.get_content_type() in {"message/rfc822", "message/global"}:
        nested = part.get_payload()
        if isinstance(nested, list) and nested and isinstance(nested[0], Message):
            return nested[0].as_bytes()
        return None
    payload = part.get_payload(decode=True)
    return bytes(payload) if isinstance(payload, (bytes, bytearray)) and payload else None


async def _localize_remote_post_commit(
    *,
    ticket_id: uuid.UUID,
    message_id: uuid.UUID,
    body_html: str | None,
) -> None:
    """H-2: post-commit локализация внешних ``http(s)://`` картинок.

    Тикет/сообщение уже атомарно закоммичены в ``_ingest_message``. Здесь, в
    **отдельной** сессии, мы выкачиваем удалённые картинки (медленный httpx +
    редиректы + таймауты), сохраняем их как ``HelpdeskAttachment`` и
    переписываем ``src`` в ``message.body_html``. Это выводит remote-fetch из
    основной DB-транзакции, чтобы письмо с множеством ``<img>`` не держало
    DB-соединение минутами (pool exhaustion).

    Best-effort: при ошибке шага письмо остаётся созданным, картинки остаются
    внешними (CSP пропустит https; http останется битым src — как и до фикса).
    """
    if not body_html:
        return
    # Ранний выход, если remote-картинок вообще нет — не открываем сессию.
    from app.services.helpdesk.email_images import find_img_sources

    has_remote = any(
        s.strip().lower().startswith(("http://", "https://")) for s in find_img_sources(body_html)
    )
    if not has_remote:
        return

    from app.core.database import AsyncSessionLocal
    from app.services.helpdesk.attachments import _TotalTracker
    from app.services.helpdesk.email_images import localize_remote_images

    try:
        async with AsyncSessionLocal() as session:
            ticket = await session.get(HelpdeskTicket, ticket_id)
            message = await session.get(HelpdeskMessage, message_id)
            if ticket is None or message is None:
                return
            updated = await localize_remote_images(
                session,
                ticket=ticket,
                message=message,
                html=body_html,
                total_tracker=_TotalTracker(),
            )
            if updated != body_html:
                message.body_html = updated
                message.body_text = html_to_plain(updated) or message.body_text
                # description первого сообщения синхронизируем с новым html.
                if ticket.description_html:
                    ticket.description_html = updated
                    ticket.description = message.body_text
            await session.commit()
    except Exception as exc:
        # Best-effort: сбой post-commit шага не должен ронять ingress письма
        # (оно уже создано и залогировано).
        logger.warning(
            "helpdesk.ingress.remote_localize_failed",
            ticket_id=str(ticket_id),
            error=str(exc),
        )


def _parse_inbound_headers(
    msg: Message,
    *,
    support_address: str | None = None,
    reply_to_address: str | None = None,
) -> dict:
    """Декодирует и нормализует заголовки входящего письма (RFC 2047).

    Кириллические Subject/From приходят как ``=?koi8-r?B?...?=`` / ``=?utf-8?B?...?=``
    — без декодирования тема тикета сохранялась бы нечитаемой
    (см. ``threading.decode_mime_header``).

    ``support_address``/``reply_to_address`` и отправитель выкидываются из
    участников-получателей (``To`` ∪ ``Cc``, миграция 083): ответ «всем» не
    должен уходить в собственный ящик (петля/дубль), а заявитель уже и так
    первый участник тикета.
    """
    subject_raw = threading_utils.decode_mime_header(msg.get("Subject"))
    from_raw = threading_utils.decode_mime_header(msg.get("From"))
    sender_email = threading_utils.normalize_email(from_raw)
    support_emails = [a for a in (support_address, reply_to_address) if a]
    return {
        "references": threading_utils.extract_references(msg),
        "subject_raw": subject_raw,
        "from_raw": from_raw,
        "subject_token": threading_utils.extract_subject_token(subject_raw),
        "recipient_token": threading_utils.extract_recipient_token(msg),
        "sender_email": sender_email,
        "sender_name": threading_utils.extract_display_name(from_raw),
        # extract_cc возвращает list[CcRecipient] (audit [L10]); сериализуем в
        # list[dict] для JSONB-колонки payload (Pydantic-модель не JSON-native).
        "cc": [
            c.model_dump()
            for c in threading_utils.extract_cc(
                msg, exclude=support_emails, exclude_sender=sender_email
            )
        ],
    }


def _apply_requester_reply(ticket: HelpdeskTicket) -> None:
    """Сменить статус тикета по машине состояний при ответе заявителя.

    ``new``/``open``/``pending`` → reopen-переходы; ``closed`` → reopen-on-closed
    со сбросом ``closed_at`` / ``closed_by_user_id`` при необходимости.
    """
    if ticket.status in REQUESTER_REOPEN_STATUSES:
        result = requester_reply(ticket.status)
        ticket.status = result.status
    elif ticket.status == HelpdeskStatus.closed:
        result = requester_reply_on_closed(ticket.closed_at)
        ticket.status = result.status
        if result.cleared_closed:
            ticket.closed_at = None
            ticket.closed_by_user_id = None


def _build_inbound_helpdesk_message(
    *,
    ticket: HelpdeskTicket,
    requester: User | None,
    headers: dict,
    message_id: str,
    body_text: str,
    body_html: str,
) -> HelpdeskMessage:
    """Конструктор ``HelpdeskMessage`` для входящего письма."""
    return HelpdeskMessage(
        ticket_id=ticket.id,
        author_user_id=requester.id if requester else None,
        author_email=headers["sender_email"],
        author_name=headers["sender_name"],
        direction=HelpdeskDirection.inbound,
        body_text=body_text,
        body_html=body_html,
        source=HelpdeskSource.email,
        email_message_id=message_id,
        in_reply_to=headers["references"][0] if headers["references"] else None,
        # Участники-получатели входящего письма (To ∪ Cc, миграция 083): ящик
        # поддержки/reply-to и отправитель уже выкинуты в
        # ``_parse_inbound_headers`` → здесь без доп. фильтрации.
        cc=headers.get("cc") or None,
    )


async def _dispatch_ingest_notifications(
    db: AsyncSession,
    redis: Redis,
    *,
    new_status: str,
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    body_text: str,
) -> None:
    """Post-commit уведомления: in-app, email-агентам, MAX-messenger.

    Все каналы — best-effort: сбой одного не роняет остальные и не влияет на
    уже закоммиченный тикет. Для новой заявки шлём email- и MAX-уведомления
    агентам; для ответа клиента по существующему тикету — email-уведомление
    агенту (зеркало in-app). MAX при ответе клиента не шлётся — он только для
    новых заявок (сознательное решение: общий чат поддержки не должен
    зашумляться репликами переписки).
    """
    # In-app уведомление агентам/assignee.
    try:
        from app.services.helpdesk.notifications import (
            notify_requester_reply,
            notify_ticket_created,
        )

        if new_status == "created":
            await notify_ticket_created(db, redis, ticket=ticket)
        else:
            await notify_requester_reply(db, redis, ticket=ticket, body_preview=body_text[:200])
    except Exception as exc:
        logger.warning("helpdesk.ingress.notify_failed", error=str(exc))

    if new_status == "created":
        # Email-уведомление агентам о новой заявке (через outbox ``kind=generic`` —
        # не требует настроенного mailbox).
        try:
            from app.services.helpdesk.notifications import (
                notify_ticket_created_email,
            )

            await notify_ticket_created_email(db, ticket=ticket, first_message=message)
        except Exception as exc:
            logger.warning("helpdesk.ingress.notify_email_failed", error=str(exc))

        # MAX-messenger уведомление в общий чат поддержки (через ``messenger_outbox``).
        # Только при включённом канале.
        try:
            from app.services.helpdesk.notifications import (
                notify_ticket_created_max,
            )

            await notify_ticket_created_max(db, ticket=ticket, first_message=message)
        except Exception as exc:
            logger.warning("helpdesk.ingress.notify_max_failed", error=str(exc))
    else:
        # Ответ клиента по существующему тикету → email-уведомление агенту
        # (зеркало in-app ``notify_requester_reply``, email-каналом через outbox
        # ``kind=generic``). Best-effort, как и все каналы здесь.
        try:
            from app.services.helpdesk.notifications import (
                notify_requester_reply_email,
            )

            await notify_requester_reply_email(db, ticket=ticket, message=message)
        except Exception as exc:
            logger.warning("helpdesk.ingress.notify_email_failed", error=str(exc))


@dataclass(frozen=True, slots=True)
class _IngestMatch:
    """Результат шага parse+match (шаг 1 декомпозиции ``_ingest_message``).

    Несёт всё, что нужно последующим шагам: разобранные заголовки, найденный
    тикет (``None`` → будет создан новый), заявку-инициатора и нормализованные
    тела письма. Неизменяемый — шаги не мутируют чужое состояние.
    """

    headers: dict
    ticket: HelpdeskTicket | None
    requester: User | None
    body_text: str
    body_html: str


@dataclass(frozen=True, slots=True)
class _IngestPersist:
    """Результат шага persist (шаг 2): созданный/апдейтнутый тикет + сообщение.

    ``new_status`` — ``"created"`` (новый тикет) или ``"appended"`` (ответ).
    ``localized_html``/``total_tracker`` — результат in-tx локализации картинок
    (без remote-fetch, см. H-2); tracker нужен для cleanup при rollback.
    """

    ticket: HelpdeskTicket
    message: HelpdeskMessage
    new_status: str
    localized_html: str | None
    total_tracker: _TotalTracker


async def _parse_and_match(
    db: AsyncSession,
    msg: Message,
    settings_row: HelpdeskMailboxSettings,
) -> _IngestMatch:
    """Шаг 1: разобрать заголовки, найти тикет, заявку и тела письма.

    ``keep_forward``: для НОВОЙ заявки (нет матча с тикетом) forward-блок письма
    не отрезается — это часто суть обращения (bounce, пересланный контекст). Для
    ответа на существующий тикет forward режется как цитата (чтобы не дублировать
    прошлое письмо в ленте). ``_extract_bodies`` возвращает ``str | None``; пустое
    тело валидно (напр. только вложения) — нормализуем в ``""``.
    """
    headers = _parse_inbound_headers(
        msg,
        support_address=settings_row.support_address,
        reply_to_address=settings_row.support_reply_to,
    )

    ticket = await _match_ticket(
        db,
        references=headers["references"],
        subject_token=headers["subject_token"],
        recipient_token=headers["recipient_token"],
        sender_email=headers["sender_email"],
    )
    requester = await _find_user_by_email(db, headers["sender_email"])

    body_text, body_html = _extract_bodies(
        msg,
        keep_forward=ticket is None,
        ticket_number=ticket.number if ticket is not None else None,
    )
    return _IngestMatch(
        headers=headers,
        ticket=ticket,
        requester=requester,
        body_text=body_text or "",
        body_html=body_html or "",
    )


async def _persist_ticket_and_message(
    db: AsyncSession,
    msg: Message,
    match: _IngestMatch,
    message_id: str,
) -> _IngestPersist:
    """Шаг 2: создать/апдейтнуть тикет + сообщение и локализовать картинки (in-tx).

    Для нового тикета — ``HelpdeskTicket`` + ``new_status="created"`` (со ссылкой
    на архивный, если ``subject_token`` указывал на него). Для ответа — смена
    статия по машине (``_apply_requester_reply``) + ``new_status="appended"``.

    In-tx локализация картинок (H-2): только inline ``cid:`` и обычные вложения
    (локальные операции FS+DB); медленный remote-http(s) fetch вынесен в шаг 3
    post-commit, чтобы не держать DB-транзакцию минутами. ``total_tracker`` (H-5)
    регистрирует пути записанных файлов для cleanup при rollback.
    """
    body_text = match.body_text
    body_html = match.body_html

    if match.ticket is None:
        # Новый тикет. Если subject_token указывал на архивный — сохраним ссылку.
        subject_token = match.headers["subject_token"]
        ref_archived = subject_token if subject_token is not None else None
        ticket = HelpdeskTicket(
            subject=_derive_subject(match.headers["subject_raw"]),
            description=body_text,
            description_html=body_html,
            status=HelpdeskStatus.new,
            source=HelpdeskSource.email,
            requester_user_id=match.requester.id if match.requester else None,
            requester_email=match.headers["sender_email"],
            requester_name=match.headers["sender_name"],
            references_archived_ticket_number=ref_archived,
        )
        db.add(ticket)
        await db.flush()
        new_status = "created"
    else:
        # Ответ на существующий тикет → сменить статус по машине.
        ticket = match.ticket
        _apply_requester_reply(ticket)
        new_status = "appended"

    message = _build_inbound_helpdesk_message(
        ticket=ticket,
        requester=match.requester,
        headers=match.headers,
        message_id=message_id,
        body_text=body_text,
        body_html=body_html,
    )
    db.add(message)
    await db.flush()  # message.id нужен для привязки вложений/локализации картинок
    ticket.last_activity_at = func.now()

    attachment_warnings: list[str] = []
    localized_html, total_tracker = await _localize_attachments_and_images(
        db,
        msg=msg,
        ticket=ticket,
        message=message,
        body_html=body_html,
        include_remote=False,
        attachment_warnings=attachment_warnings,
    )
    # ``match.body_html`` is an intermediate sanitized value that may still
    # contain ``cid:``. Persist only the regular sanitizer result after exact
    # CID references have been rewritten to local authenticated URLs.
    safe_html = sanitize_html(localized_html) if localized_html is not None else ""
    safe_text = html_to_plain(safe_html) or body_text
    message.body_html = safe_html
    message.body_text = safe_text
    if new_status == "created":
        ticket.description_html = safe_html
        ticket.description = safe_text
    message.attachment_warnings = attachment_warnings
    return _IngestPersist(
        ticket=ticket,
        message=message,
        new_status=new_status,
        localized_html=safe_html,
        total_tracker=total_tracker,
    )


async def _finalize_ingest(
    db: AsyncSession,
    redis: Redis,
    match: _IngestMatch,
    persist: _IngestPersist,
    message_id: str,
    summary: dict,
) -> None:
    """Шаг 3: применить локализованный html, закоммитить и разослать уведомления.

    Инварианты (см. characterization-тесты ``test_helpdesk_ingress_tx.py``):

    * **Единый commit** — ``helpdesk_email_log`` и (для нового тикета) email
      заявителю добавляются в сессию **до** ``db.commit()``. Раньше лог писался
      отдельным коммитом → сбой между ними → дубль письма (split-commit баг).
    * **Cleanup файлов-сирот (H-5)** — при rollback файлы, записанные локализацией,
      удаляются (``ticket.number`` уже потрачен, без cleanup папка ``TKT-{n}`` течёт).
    * **Post-commit remote-localize (H-2)** — медленный httpx-fetch внешних картинок
      в отдельной сессии **после** коммита; здесь — лишь инициация.
    * **Уведомления** — in-app/email/MAX, best-effort (``_dispatch_ingest_notifications``).
    """
    body_text = match.body_text
    body_html = match.body_html
    localized_html = persist.localized_html

    try:
        if localized_html is not None and localized_html != body_html:
            persist.message.body_html = localized_html
            # Деривация plain из обновлённого html (картинки стали относительными).
            persist.message.body_text = html_to_plain(localized_html) or body_text
            body_text = persist.message.body_text
            if persist.new_status == "created":
                # description — копия первого сообщения, синхронизируем.
                persist.ticket.description = body_text
                persist.ticket.description_html = localized_html

        # Идемпотентный лог пишется В ТОЙ ЖЕ транзакции, что и сообщение
        # (outbox-style инвариант): раньше бизнес-коммит сообщения и запись
        # helpdesk_email_log (отдельный commit в _write_log) были в разных
        # транзакциях — сбой между ними → письмо создано, но не залогировано →
        # повторная обработка / дубль. Теперь единый commit.
        db.add(
            HelpdeskEmailLog(
                message_id=message_id,
                ticket_id=persist.ticket.id,
                message_db_id=persist.message.id,
                status=persist.new_status,
                error=None,
            )
        )
        # Email заявчику «заявка зарегистрирована» — только для новых тикетов
        # (не для ответов на существующие). В ту же транзакцию, что и создание
        # (outbox-инвариант AGENTS.md). Best-effort: сбой enqueue (нет mailbox)
        # не роняет создание тикета — тикет/сообщение/лог коммитятся без письма.
        if persist.new_status == "created":
            from app.services.helpdesk.tickets import _try_enqueue_created_email

            await _try_enqueue_created_email(db, ticket=persist.ticket)
        await db.commit()
    except BaseException:
        # H-5: при rollback транзакции файлы-сирота (записанные в FS, но без
        # закоммиченной DB-строки) удаляются. identity ``ticket.number`` уже
        # потрачен и не переиспользуется → без cleanup папка TKT-{n} течёт.
        await db.rollback()
        cleanup_recorded_files(persist.total_tracker)
        raise
    await db.refresh(persist.message)
    summary[persist.new_status] += 1

    # H-2: post-commit локализация внешних http(s) картинок. Тикет/сообщение
    # уже атомарно закоммичены (outbox-инвариант соблюдён). Remote-fetch
    # выполняется в отдельной сессии — медленные HTTP-запросы не держат
    # основную транзакцию. Best-effort: если шаг упадёт, письмо уже создано,
    # картинки останутся внешними (CSP пропустит https; http — битый src).
    await _localize_remote_post_commit(
        ticket_id=persist.ticket.id,
        message_id=persist.message.id,
        body_html=localized_html if localized_html is not None else body_html,
    )

    await _dispatch_ingest_notifications(
        db,
        redis,
        new_status=persist.new_status,
        ticket=persist.ticket,
        message=persist.message,
        body_text=body_text,
    )


async def _ingest_message(
    db: AsyncSession,
    redis: Redis,
    msg: Message,
    message_id: str,
    settings_row: HelpdeskMailboxSettings,
    summary: dict,
) -> None:
    """Оркестратор email-ingress: разобрать → сопоставить → сохранить → финализировать.

    Тонкий wiring из трёх шагов (декомпозиция [M6], поведение 1:1 с исходным
    монолитом — см. characterization-тесты ``test_helpdesk_ingress_tx.py``):

    1. ``_parse_and_match`` — заголовки, тикет, заявка, тела.
    2. ``_persist_ticket_and_message`` — тикет+сообщение+in-tx локализация.
    3. ``_finalize_ingest`` — commit-инвариант + post-commit + уведомления.
    """
    match = await _parse_and_match(db, msg, settings_row)
    persist = await _persist_ticket_and_message(db, msg, match, message_id)
    await _finalize_ingest(db, redis, match, persist, message_id, summary)


async def _match_ticket(
    db: AsyncSession,
    *,
    references: list[str],
    subject_token: int | None,
    recipient_token: int | None = None,
    sender_email: str = "",
) -> HelpdeskTicket | None:
    """Найти живой тикет по references (основной), subject-token или
    recipient-token (fallback'и). ``None`` → новый тикет.

    Порядок: References/In-Reply-To → ``[#TKT-NN]`` в теме → ``+TKT-NN`` в
    адресе получателя. Каждый следующий способ используется только если
    предыдущие не дали матча.

    Безопасность (email-инъекция в чужой тикет): ``subject_token`` и
    ``recipient_token`` — угадываемые (number последователен). Без сверки
    отправителя стороннее письмо с ``[#TKT-123]`` в теме могло подмешать
    сообщение в чужой тикет. Теперь для этих fallback'ов отправитель должен
    совпадать с ``ticket.requester_email`` (case-insensitive). ``references``
    — основной матч, несёт секретный ``Message-ID`` исходящего письма (не
    угадывается) → сверка отправителя не требуется.
    """
    if references:
        res = await db.execute(
            select(HelpdeskTicket)
            .join(HelpdeskMessage, HelpdeskMessage.ticket_id == HelpdeskTicket.id)
            .where(HelpdeskMessage.email_message_id.in_(references))
            .limit(1)
        )
        ticket = res.scalars().first()
        if ticket is not None:
            return ticket
    # Fallback'и по угадываемому токену — только если отправитель = заявитель.
    token = subject_token if subject_token is not None else recipient_token
    if token is None:
        return None
    res = await db.execute(select(HelpdeskTicket).where(HelpdeskTicket.number == token).limit(1))
    ticket = res.scalars().first()
    if ticket is None:
        return None
    if (
        sender_email
        and ticket.requester_email
        and sender_email.lower() != ticket.requester_email.lower()
    ):
        # Отправитель не совпадает с заявителем → не подмешиваем в чужой тикет,
        # создаём новый (со ссылкой references_archived_ticket_number, если
        # исходный тикет архивный — обрабатывается в _ingest_message).
        #
        # H-11: не логируем PII (адреса) в открытом виде — маскируем по образцу
        # AGENTS.md (email-хеш для rate-limit). Диагностики «токен + домены + факт
        # расхождения» достаточно для разбора; полный адрес — только в БД/почте.
        logger.info(
            "helpdesk.ingress.token_sender_mismatch",
            ticket_number=ticket.number,
            sender_domain=_email_domain(sender_email),
            requester_domain=_email_domain(ticket.requester_email),
        )
        return None
    return ticket


def _email_domain(email: str) -> str:
    """Маскированный email для логов: ``user@company.local`` → ``u***@company.local``.

    Часть до ``@`` никогда не возвращается полностью (PII). Домен оставляем —
    он нужен для диагностики («письмо пришло снаружи организации»)."""
    if "@" not in email:
        return "(invalid)"
    local, _, domain = email.partition("@")
    if not local:
        return f"@{domain or '(empty)'}"
    return f"{local[0]}***@{domain or '(empty)'}"


async def _find_user_by_email(db: AsyncSession, email: str) -> User | None:
    if not email:
        return None
    res = await db.execute(
        select(User).where(func.lower(User.email) == email.lower(), User.deleted_at.is_(None))
    )
    return res.scalars().first()


def _derive_subject(raw: str | None) -> str:
    """Тема тикета из ``Subject`` письма с удалением токена ``[#TKT-...]``.

    Токен добавляется исходящими письмами портала; во входящем не нужен
    (матчинг уже выполнен). Через публичный ``threading.strip_subject_token``
    (раньше лезли в приватный ``_SUBJECT_TOKEN_RE``).
    """
    return threading_utils.strip_subject_token(raw or "") or "(без темы)"


def _select_body_parts(msg: Message) -> tuple[str | None, str | None]:
    """Выбрать внешние body alternatives, не заходя во вложенные ``message/*``."""

    def visit(part: Message, *, root: bool = False) -> tuple[str | None, str | None]:
        disposition = (part.get_content_disposition() or "").lower()
        if not root and (disposition == "attachment" or part.get_content_maintype() == "message"):
            return None, None
        if not part.is_multipart():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                return _decode_payload(part), None
            if content_type == "text/html":
                return None, _decode_payload(part)
            return None, None

        payload = part.get_payload()
        if not isinstance(payload, list):
            return None, None
        plain: str | None = None
        html: str | None = None
        for child in payload:
            if not isinstance(child, Message):
                continue
            child_plain, child_html = visit(child)
            plain = plain if plain is not None else child_plain
            html = html if html is not None else child_html
            if plain is not None and html is not None:
                break
        return plain, html

    return visit(msg, root=True)


def _extract_bodies(
    msg: Message,
    *,
    keep_forward: bool = False,
    ticket_number: int | None = None,
) -> tuple[str, str | None]:
    """Extract bodies; HTML is safe intermediate data with temporary ``cid:``.

    Инвариант: если есть HTML — он же источник истины для ``plain`` (как в
    ``normalize_message_bodies``). Это гарантирует, что подпись/цитата, отрезанные
    из HTML, отсутствуют и в ``plain`` (а значит — в ``body_text``,
    ``description``, MAX- и email-уведомлениях). Для писем без HTML (text/plain
    only) возвращается оригинальный plain после ``strip_quoted_reply``.

    Final storage sanitization runs after exact CID localization. ``keep_forward``
    — для **новых** заявок (нет матча с существующим тикетом):
    forward-блок письма (``-----Original Message-----``, Outlook ``From:/Sent:``,
    Gmail ``wrote:``) не отрезается. Для новой заявки forward — часто суть
    обращения (bounce об ошибке доставки, пересланный контекст проблемы), а не
    цитата. См. ``email_quote.strip_quoted_reply`` (параметр ``keep_forward``).
    Маркер ``REPLY_MARKER_TOKEN`` режется всегда — он проставляется только
    исходящими письмами портала, его наличие = ответ на наш тикет.
    """
    plain, html = _select_body_parts(msg)
    # Outlook commonly moves the known logo URL from HTML into MIME metadata.
    # Structural extraction excludes attached message/rfc822 subtrees.
    from app.services.helpdesk.email_images import extract_inline_parts

    inline_parts = extract_inline_parts(msg)
    cid_names = {
        cid: tuple(name for name in (part.filename, part.content_location) if name)
        for cid, part in inline_parts.items()
    }

    # Отсечение цитаты предыдущего письма (маркер-разделитель + эвристика).
    # До санитации HTML — чтобы поймать quote-контейнеры по классам до того,
    # как nh3 их переформатирует. См. ``email_quote``.
    # ``keep_forward``: для новых заявок forward-блок не режется (суть обращения).
    if plain is not None:
        plain = strip_quoted_reply(
            plain,
            keep_forward=keep_forward,
            ticket_number=ticket_number,
        )
        plain = strip_plain_signature(plain, preserve_forward=keep_forward)
    if html is not None:
        html = strip_quoted_html(
            html,
            keep_forward=keep_forward,
            ticket_number=ticket_number,
        )

    # Отсечение корпоративной подписи (логотип Mage_Ru.png + фирменные цвета).
    # После снятия цитаты (цитата может содержать подпись отправителя — её
    # снимет ``strip_quoted_html``, оставив только «живой» хвост с актуальной
    # подписью автора ответа). См. ``email_signature``.
    if html is not None:
        html = strip_email_signature(html, cid_names=cid_names)

    # HTML — источник истины (как ``normalize_message_bodies``): если html есть,
    # ``plain`` **всегда** деривируется из уже очищенного html, а не берётся из
    # исходной text/plain-части письма. Раньше для ``multipart/alternative``
    # (доминирующий формат Outlook — plain+html копии в одном письме) исходный
    # ``plain`` сохранялся как есть, без отсечения подписи (подпись в text/plain
    # не содержит уникальных HTML-маркеров), и улетал в ``body_text`` → в MAX-
    # уведомление о новой заявке (баг 20.07.2026). Единый инвариант «plain —
    # дериват из чистого html» консистентен для всех даунстримов: web-лента
    # (``body_html``), email-нотификации агентам (``_message_body_html``), MAX.
    if html is not None:
        html = sanitize_email_html_for_localization(html)
        # ``strip_quoted_reply`` повторно: html-цитата могла оставить
        # «On … wrote:» / заголовки Outlook и после снятия тегов.
        plain = strip_quoted_reply(
            html_to_plain(html),
            keep_forward=keep_forward,
            ticket_number=ticket_number,
        )
    return (plain or "").strip() or "(пустое сообщение)", html


def _decode_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, (bytes, bytearray)):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return bytes(payload).decode(charset, errors="replace")
    except (LookupError, TypeError):
        return bytes(payload).decode("utf-8", errors="replace")


# ── Email log helpers ────────────────────────────────────────────────────────


async def _fetch_log(db: AsyncSession, message_id: str) -> HelpdeskEmailLog | None:
    res = await db.execute(
        select(HelpdeskEmailLog).where(HelpdeskEmailLog.message_id == message_id)
    )
    return res.scalars().one_or_none()


async def _write_log(
    db: AsyncSession,
    message_id: str,
    ticket_id: uuid.UUID | None,
    message_db_id: uuid.UUID | None,
    *,
    status: str,
    error: str | None,
    commit: bool = True,
) -> None:
    """Записать строку в ``helpdesk_email_log``.

    Используется для anti-loop skip (нет бизнес-операции → отдельная транзакция,
    ``commit=True``). Для успешного ingest лог добавляется в той же транзакции
    внутри ``_ingest_message`` (этот путь ``_write_log`` не вызывает).
    """
    log = HelpdeskEmailLog(
        message_id=message_id,
        ticket_id=ticket_id,
        message_db_id=message_db_id,
        status=status,
        error=error,
    )
    db.add(log)
    if commit:
        await db.commit()
