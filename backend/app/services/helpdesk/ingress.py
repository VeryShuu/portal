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
import re
import uuid
from contextlib import suppress
from email import message_from_bytes
from email.message import Message
from email.utils import getaddresses
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.sanitize import sanitize_html
from app.models.helpdesk import (
    HelpdeskEmailLog,
    HelpdeskMailboxSettings,
    HelpdeskMessage,
    HelpdeskTicket,
)
from app.models.user import User
from app.services.helpdesk import threading as threading_utils
from app.services.helpdesk.attachments import cleanup_recorded_files
from app.services.helpdesk.email_quote import html_to_plain, strip_quoted_html, strip_quoted_reply
from app.services.helpdesk.lifecycle import (
    REQUESTER_REOPEN_STATUSES,
    requester_reply,
    requester_reply_on_closed,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from app.services.helpdesk.attachments import _TotalTracker

logger = get_logger(__name__)

LAST_POLL_KEY = "helpdesk:imap:last_poll_at"
POLL_LOCK_KEY = "helpdesk:imap:poll_lock"
POLL_LOCK_TTL = 300  # 5 минут

# Литера размера IMAP- literal: '{3194}' в маркере FETCH перед телом письма.
_LITERAL_RE = re.compile(rb"\{\d+\}")


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


# ── Connection probe ─────────────────────────────────────────────────────────


def _make_imap_client_raw(*, host: str, port: int, use_ssl: bool) -> Any:
    """Создать ``aioimaplib`` клиент по host/port/ssl (без подключения)."""
    import aioimaplib

    if use_ssl:
        return aioimaplib.IMAP4_SSL(host=host, port=port)
    return aioimaplib.IMAP4(host=host, port=port)


def _make_imap_client(settings_row: HelpdeskMailboxSettings) -> Any:
    return _make_imap_client_raw(
        host=settings_row.imap_host,
        port=settings_row.imap_port,
        use_ssl=settings_row.imap_use_ssl,
    )


async def probe_imap_connection(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    use_ssl: bool,
    folder: str,
) -> tuple[bool, str]:
    """Проверка IMAP-соединения для ``POST /settings/mailbox/test``.
    Возвращает ``(ok, detail)``."""
    try:
        client = _make_imap_client_raw(host=host, port=port, use_ssl=use_ssl)
        await asyncio.wait_for(client.wait_hello_from_server(), timeout=10)
        await asyncio.wait_for(client.login(username, password), timeout=10)
        # Выбор папки — финальная проверка доступности.
        resp = await client.select(folder)
        ok = "OK" in resp[0] if resp else False
        await client.logout()
        if ok:
            return True, f"Connected, selected '{folder}'"
        return False, f"select failed: {resp}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


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
                with suppress(Exception):
                    await db.rollback()
                # Помечаем прочитанным, но не удаляем — оставляем для разбора.
                # (Фильтр по \Seen больше не используется, но сохраняем флаг для
                # совместимости с почтовыми клиентами оператора.)
                await _safe_seen(client, uid)
        # Физически удалить письма, помеченные \Deleted через _safe_delete
        # (работает только при settings_row.delete_after_fetch). Без EXPUNGE
        # STORE +FLAGS \Deleted лишь вешает флаг, но письмо остаётся в папке.
        if settings_row.delete_after_fetch and uids:
            with suppress(Exception):
                await client.expunge()
    finally:
        with suppress(Exception):
            await client.logout()

    logger.info("helpdesk.ingress.poll_done", **summary)
    return summary


def _decrypt_password(row: HelpdeskMailboxSettings) -> str | None:
    try:
        from app.core.secret_crypto import decrypt_secret

        return decrypt_secret(row.imap_password_enc)
    except Exception:
        logger.exception("helpdesk.ingress.password_decrypt_failed")
        return None


async def _search_all(client: Any) -> list[str]:
    r"""Список UID'ов всех писем текущей папки (``SEARCH ALL``).

    В отличие от ``SEARCH UNSEEN``, забирает и уже прочитанные письма —
    оператор читает ящик вручную, и ``\Seen``-письма иначе терялись бы.
    Дедупликация — на уровне ``helpdesk_email_log`` в ``_process_uid``."""
    typ, data = await client.search("ALL")
    if typ != "OK":
        return []
    # data — список с одной bytes-строкой UID'ов через пробел.
    if not data or not data[0]:
        return []
    raw = data[0]
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="ignore")
    return [u for u in raw.split() if u]


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


def _extract_rfc822(data: Any) -> bytes | None:
    """Извлечь тело RFC822 из ответа ``FETCH``.

    ``aioimaplib`` отдаёт данные **плоским списком**, чередующим маркеры и
    полезную нагрузку::

        [b'1 FETCH (RFC822 {3194}', bytearray(b'<RFC822...>'), b')', b'OK ...']

    Маркер перед телом содержит литерал размера ``{NNN}``; следующий за ним
    элемент — само тело (``bytes``/``bytearray``). Берём элемент, идущий сразу
    после маркера с ``{...}``.

    Ранее функция искала ``tuple`` в данных (старый формат ответа), но
    aioimaplib так не форматирует ``FETCH`` — поэтому возвращался ``None``,
    ``message_from_bytes(None)`` падал с ``AttributeError``, и ingress молча
    помечал каждое письмо ошибкой (``errors += 1``), не создавая тикет.
    """
    items = list(data)

    # 1) Плоский формат aioimaplib: тело идёт сразу после маркера с '{NNN}'.
    for i, item in enumerate(items):
        if isinstance(item, (bytes, bytearray)) and b"{" in item and b"}" in item:
            preview = bytes(item)
            if _LITERAL_RE.search(preview) and i + 1 < len(items):
                body = items[i + 1]
                if isinstance(body, (bytes, bytearray)):
                    return bytes(body)

    # 2) Совместимость со старым tuple-формататом: (marker, body).
    for item in items:
        if isinstance(item, tuple):
            for part in item:
                if isinstance(part, (bytes, bytearray)) and not _LITERAL_RE.search(bytes(part)):
                    return bytes(part)

    return None


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

    # Обычные вложения (Content-Disposition: attachment) — сохранить в FS.
    for part in msg.walk():
        disp = (part.get_content_disposition() or "").lower()
        if disp != "attachment":
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            continue
        # Имя файла декодируем из RFC 2047 encoded-words (=?UTF-8?B?...?=), иначе
        # original_name сохранится нечитаемым (Subject/From уже декодируются
        # выше через decode_mime_header — тот же механизм).
        raw_name = part.get_filename() or "attachment"
        original = threading_utils.decode_mime_header(raw_name) or "attachment"
        await save_image_bytes(
            db,
            ticket=ticket,
            message_id=message.id,
            data=bytes(payload),
            original_name=original,
            total_tracker=total_tracker,
        )

    if not body_html:
        return body_html, total_tracker
    updated = await localize_images(
        db,
        ticket=ticket,
        message=message,
        html=body_html,
        inline_map=inline_map,
        total_tracker=total_tracker,
        include_remote=include_remote,
    )
    return updated, total_tracker


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


async def _ingest_message(
    db: AsyncSession,
    redis: Redis,
    msg: Message,
    message_id: str,
    settings_row: HelpdeskMailboxSettings,
    summary: dict,
) -> None:
    references = threading_utils.extract_references(msg)
    # Декодируем заголовки (RFC 2047 encoded-words): кириллические Subject/From
    # приходят как =?koi8-r?B?...?= / =?utf-8?B?...?= — без декодирования
    # тема тикета сохранялась бы нечитаемой (см. threading.decode_mime_header).
    subject_raw = threading_utils.decode_mime_header(msg.get("Subject"))
    from_raw = threading_utils.decode_mime_header(msg.get("From"))
    subject_token = threading_utils.extract_subject_token(subject_raw)
    recipient_token = threading_utils.extract_recipient_token(msg)

    sender_email = threading_utils.normalize_email(from_raw)
    sender_name = threading_utils.extract_display_name(from_raw)

    ticket = await _match_ticket(
        db,
        references=references,
        subject_token=subject_token,
        recipient_token=recipient_token,
        sender_email=sender_email,
    )

    requester = await _find_user_by_email(db, sender_email)

    body_text, body_html = _extract_bodies(msg)

    if ticket is None:
        # Новый тикет. Если subject_token указывал на архивный — сохраним ссылку.
        ref_archived = None
        if subject_token is not None:
            ref_archived = subject_token  # нет живого тикета → продолжение архивного
        ticket = HelpdeskTicket(
            subject=_derive_subject(subject_raw),
            description=body_text,
            description_html=body_html,
            status="new",
            source="email",
            requester_user_id=requester.id if requester else None,
            requester_email=sender_email,
            requester_name=sender_name,
            references_archived_ticket_number=ref_archived,
        )
        db.add(ticket)
        await db.flush()
        new_status = "created"
    else:
        # Ответ на существующий тикет → сменить статус по машине.
        if ticket.status in REQUESTER_REOPEN_STATUSES:
            result = requester_reply(ticket.status)
            ticket.status = result.status
        elif ticket.status == "closed":
            result = requester_reply_on_closed(ticket.closed_at)
            ticket.status = result.status
            if result.cleared_closed:
                ticket.closed_at = None
                ticket.closed_by_user_id = None
        new_status = "appended"

    message = HelpdeskMessage(
        ticket_id=ticket.id,
        author_user_id=requester.id if requester else None,
        author_email=sender_email,
        author_name=sender_name,
        direction="inbound",
        visibility="public",
        body_text=body_text,
        body_html=body_html,
        source="email",
        email_message_id=message_id,
        in_reply_to=references[0] if references else None,
    )
    db.add(message)
    await db.flush()  # message.id нужен для привязки вложений/локализации картинок
    ticket.last_activity_at = func.now()

    # Локализация картинок + обычные вложения. Снимает MVP-заглушку: раньше
    # email-вложения не сохранялись, а inline cid: / внешние http(s) картинки
    # ломались (битая иконка / CSP-блок). Теперь все картинки локализуются в
    # FS (attachments), src переписываются на /api/v1/helpdesk/attachments/{id}.
    #
    # H-2: remote http(s) картинки локализуем POST-COMMIT (отдельная сессия),
    # не в этой транзакции — иначе медленный httpx-fetch держит DB-соединение
    # открытым минутами (письмо с множеством <img> → pool exhaustion). Здесь —
    # только inline cid: и обычные вложения (локальные операции FS+DB).
    #
    # H-5: ``total_tracker`` регистрирует пути записанных файлов — если commit
    # упадёт, файлы-сирота (без DB-строки) удаляются в except-блоке ниже.
    localized_html, total_tracker = await _localize_attachments_and_images(
        db, msg=msg, ticket=ticket, message=message, body_html=body_html, include_remote=False
    )
    try:
        if localized_html is not None and localized_html != body_html:
            message.body_html = localized_html
            # Деривация plain из обновлённого html (картинки стали относительными).
            message.body_text = html_to_plain(localized_html) or body_text
            body_text = message.body_text
            if new_status == "created":
                # description — копия первого сообщения, синхронизируем.
                ticket.description = body_text
                ticket.description_html = localized_html

        # Идемпотентный лог пишется В ТОЙ ЖЕ транзакции, что и сообщение
        # (outbox-style инвариант): раньше бизнес-коммит сообщения (:486) и
        # запись helpdesk_email_log (отдельный commit в _write_log) были в разных
        # транзакциях — сбой между ними → письмо создано, но не залогировано →
        # повторная обработка / дубль. Теперь единый commit.
        db.add(
            HelpdeskEmailLog(
                message_id=message_id,
                ticket_id=ticket.id,
                message_db_id=message.id,
                status=new_status,
                error=None,
            )
        )
        # Email заявителю «заявка зарегистрирована» — только для новых тикетов
        # (не для ответов на существующие). В ту же транзакцию, что и создание
        # (outbox-инвариант AGENTS.md). Best-effort: сбой enqueue (нет mailbox)
        # не роняет создание тикета — тикет/сообщение/лог коммитятся без письма.
        if new_status == "created":
            from app.services.helpdesk.tickets import _try_enqueue_created_email

            await _try_enqueue_created_email(db, ticket=ticket)
        await db.commit()
    except BaseException:
        # H-5: при rollback транзакции файлы-сирота (записанные в FS, но без
        # закоммиченной DB-строки) удаляются. identity ``ticket.number`` уже
        # потрачен и не переиспользуется → без cleanup папка TKT-{n} течёт.
        await db.rollback()
        cleanup_recorded_files(total_tracker)
        raise
    await db.refresh(message)
    summary[new_status] += 1

    # H-2: post-commit локализация внешних http(s) картинок. Тикет/сообщение
    # уже атомарно закоммичены (outbox-инвариант соблюдён). Remote-fetch
    # выполняется в отдельной сессии — медленные HTTP-запросы не держат
    # основную транзакцию. Best-effort: если шаг упадёт, письмо уже создано,
    # картинки останутся внешними (CSP пропустит https; http — битый src).
    await _localize_remote_post_commit(
        ticket_id=ticket.id,
        message_id=message.id,
        body_html=localized_html if localized_html is not None else body_html,
    )

    # In-app уведомление агентам/assignee — best-effort.
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

    # Email-уведомление агентам о новой заявке (best-effort, через outbox
    # ``kind=generic`` — не требует настроенного mailbox). Только для новых
    # тикетов: для ответов на существующий тикет агент уже оповещён in-app,
    # а email-тред ведётся отдельно с заявителем.
    if new_status == "created":
        try:
            from app.services.helpdesk.notifications import (
                notify_ticket_created_email,
            )

            await notify_ticket_created_email(db, ticket=ticket, first_message=message)
        except Exception as exc:
            logger.warning("helpdesk.ingress.notify_email_failed", error=str(exc))

        # MAX-messenger уведомление в общий чат поддержки (best-effort, через
        # ``messenger_outbox``). Только при включённом канале. Аналогично
        # email-уведомлению: только для новых тикетов, не для ответов.
        try:
            from app.services.helpdesk.notifications import (
                notify_ticket_created_max,
            )

            await notify_ticket_created_max(db, ticket=ticket, first_message=message)
        except Exception as exc:
            logger.warning("helpdesk.ingress.notify_max_failed", error=str(exc))


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


def _extract_bodies(msg: Message) -> tuple[str, str | None]:
    """Извлечь ``(text/plain, text/html|None)``. HTML — sanitized."""
    plain = None
    html = None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get_content_disposition() or "").lower()
            if disp == "attachment":
                continue
            if ctype == "text/plain" and plain is None:
                plain = _decode_payload(part)
            elif ctype == "text/html" and html is None:
                html = _decode_payload(part)
    else:
        ctype = msg.get_content_type()
        if ctype == "text/html":
            html = _decode_payload(msg)
        else:
            plain = _decode_payload(msg)

    # Отсечение цитаты предыдущего письма (маркер-разделитель + эвристика).
    # До санитизации HTML — чтобы поймать quote-контейнеры по классам до того,
    # как nh3 их переформатирует. См. ``email_quote``.
    if plain is not None:
        plain = strip_quoted_reply(plain)
    if html is not None:
        html = strip_quoted_html(html)

    if plain is None and html:
        # Деривация plain из HTML: тривиально — sanitized HTML без тегов.
        # Прогоняем через strip_quoted_reply повторно — html-цитата могла
        # оставить «On … wrote:» / заголовки Outlook и после снятия тегов.
        plain = strip_quoted_reply(html_to_plain(sanitize_html(html)))
    if html is not None:
        html = sanitize_html(html)
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


async def _safe_seen(client: Any, uid: str) -> None:
    with suppress(Exception):
        await client.store(uid, "+FLAGS", "\\Seen")


async def _safe_delete(client: Any, uid: str) -> None:
    """Пометить сообщение ``\\Deleted`` (best-effort).

    ``aioimaplib.IMAP4.delete`` — это IMAP-команда ``DELETE``, которая удаляет
    **папку целиком** по имени, а не сообщение. Для удаления письма нужно
    ``STORE +FLAGS \\Deleted`` (пометка) + ``EXPUNGE`` (физическое удаление,
    выполняется в ``poll_mailbox`` после обработки всех UID'ов).
    """
    with suppress(Exception):
        await client.store(uid, "+FLAGS", "\\Deleted")
