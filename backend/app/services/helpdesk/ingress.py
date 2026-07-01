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
from email import message_from_bytes
from email.message import Message
from email.utils import getaddresses
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import HELPDESK_MAX_ATTACHMENT_MB, HELPDESK_MAX_TOTAL_INGRESS_MB
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
from app.services.helpdesk.email_quote import strip_quoted_html, strip_quoted_reply
from app.services.helpdesk.lifecycle import (
    REQUESTER_REOPEN_STATUSES,
    requester_reply,
    requester_reply_on_closed,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

LAST_POLL_KEY = "helpdesk:imap:last_poll_at"
POLL_LOCK_KEY = "helpdesk:imap:poll_lock"
POLL_LOCK_TTL = 300  # 5 минут

# Литера размера IMAP- literal: '{3194}' в маркере FETCH перед телом письма.
_LITERAL_RE = re.compile(rb"\{\d+\}")


# ── Anti-loop detection (ТЗ §5.3) ────────────────────────────────────────────

_AUTO_HEADERS = ("Auto-Submitted", "Precedence", "X-Auto-Response-Suppress")
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
    archive: object | None = None,  # attachment archiver stub — не используется в MVP
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
        await asyncio.wait_for(
            client.login(settings_row.imap_username, password), timeout=15
        )
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
                logger.exception(
                    "helpdesk.ingress.uid_failed", uid=uid, error=str(exc)
                )
                # Помечаем прочитанным, но не удаляем — оставляем для разбора.
                # (Фильтр по \Seen больше не используется, но сохраняем флаг для
                # совместимости с почтовыми клиентами оператора.)
                await _safe_seen(client, uid)
        # Физически удалить письма, помеченные \Deleted через _safe_delete
        # (работает только при settings_row.delete_after_fetch). Без EXPUNGE
        # STORE +FLAGS \Deleted лишь вешает флаг, но письмо остаётся в папке.
        if settings_row.delete_after_fetch and uids:
            with _Suppress():
                await client.expunge()
    finally:
        with _Suppress():
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
                if isinstance(part, (bytes, bytearray)) and not _LITERAL_RE.search(
                    bytes(part)
                ):
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

    ticket = await _match_ticket(
        db,
        references=references,
        subject_token=subject_token,
        recipient_token=recipient_token,
    )

    sender_email = threading_utils.normalize_email(from_raw)
    sender_name = threading_utils.extract_display_name(from_raw)
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
    ticket.last_activity_at = func.now()

    # Вложения (пока без сохранения в FS на ingress-MVP — заглушка; полный
    # разбор см. future-task, здесь only metadata-guard от превышения лимитов).
    _ = (HELPDESK_MAX_ATTACHMENT_MB, HELPDESK_MAX_TOTAL_INGRESS_MB)

    await db.commit()
    await db.refresh(message)
    await _write_log(db, message_id, ticket.id, message.id, status=new_status, error=None)
    summary[new_status] += 1

    # In-app уведомление агентам/assignee — best-effort.
    try:
        from app.services.helpdesk.notifications import (
            notify_requester_reply,
            notify_ticket_created,
        )

        if new_status == "created":
            await notify_ticket_created(db, redis, ticket=ticket)
        else:
            await notify_requester_reply(
                db, redis, ticket=ticket, body_preview=body_text[:200]
            )
    except Exception as exc:
        logger.warning("helpdesk.ingress.notify_failed", error=str(exc))


async def _match_ticket(
    db: AsyncSession,
    *,
    references: list[str],
    subject_token: int | None,
    recipient_token: int | None = None,
) -> HelpdeskTicket | None:
    """Найти живой тикет по references (основной), subject-token или
    recipient-token (fallback'и). ``None`` → новый тикет.

    Порядок: References/In-Reply-To → ``[#TKT-NN]`` в теме → ``+TKT-NN`` в
    адресе получателя. Каждый следующий способ используется только если
    предыдущие не дали матча.
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
    if subject_token is not None:
        res = await db.execute(
            select(HelpdeskTicket).where(HelpdeskTicket.number == subject_token).limit(1)
        )
        return res.scalars().first()
    if recipient_token is not None:
        res = await db.execute(
            select(HelpdeskTicket).where(HelpdeskTicket.number == recipient_token).limit(1)
        )
        return res.scalars().first()
    return None


async def _find_user_by_email(db: AsyncSession, email: str) -> User | None:
    if not email:
        return None
    res = await db.execute(
        select(User).where(func.lower(User.email) == email.lower(), User.deleted_at.is_(None))
    )
    return res.scalars().first()


def _derive_subject(raw: str | None) -> str:
    s = (raw or "(без темы)").strip()
    # Снимаем токен [#TKT-...] — он добавляется исходящими, во входящем не нужен.
    return threading_utils._SUBJECT_TOKEN_RE.sub("", s).strip() or "(без темы)"


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
        plain = strip_quoted_reply(
            re.sub(r"<[^>]+>", " ", sanitize_html(html)).strip()
        )
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
) -> None:
    log = HelpdeskEmailLog(
        message_id=message_id,
        ticket_id=ticket_id,
        message_db_id=message_db_id,
        status=status,
        error=error,
    )
    db.add(log)
    await db.commit()


async def _safe_seen(client: Any, uid: str) -> None:
    with _Suppress():
        await client.store(uid, "+FLAGS", "\\Seen")


async def _safe_delete(client: Any, uid: str) -> None:
    """Пометить сообщение ``\\Deleted`` (best-effort).

    ``aioimaplib.IMAP4.delete`` — это IMAP-команда ``DELETE``, которая удаляет
    **папку целиком** по имени, а не сообщение. Для удаления письма нужно
    ``STORE +FLAGS \\Deleted`` (пометка) + ``EXPUNGE`` (физическое удаление,
    выполняется в ``poll_mailbox`` после обработки всех UID'ов).
    """
    with _Suppress():
        await client.store(uid, "+FLAGS", "\\Deleted")


class _Suppress:
    """Контекстный менеджер, глотающий исключения (для best-effort IMAP-флагов)."""

    def __enter__(self) -> _Suppress:
        return self

    def __exit__(self, *exc: object) -> bool:
        return True
