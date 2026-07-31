"""IMAP-поллинг ящика ERP-отчётов + post-fetch фильтрация.

Клон паттерна ``helpdesk/ingress.py``, но с фильтрацией писем (общий ящик —
на него может сыпаться разная почта). Фильтрация post-fetch (на стороне
портала), а не через IMAP ``SEARCH SUBJECT``: последний ненадёжен с MIME/
B-encoded кириллицей (``=?UTF-8?B?...?=``).

Контракт: поллинг берёт ``SEARCH UNSEEN``, для каждого письма:

1. Декодирует Subject/From (через ``decode_mime_header`` из helpdesk-threading).
2. Применяет фильтры (``mail_subject_filter`` / ``mail_sender_filter``):
   CI-подстрока. Пустой фильтр = не применяется.
3. Если письмо **мимо фильтра** → пропускаем, **НЕ** помечаем ``\\Seen``
   (не трогаем чужую почту на общем ящике).
4. Если подходит → извлекаем первое поддерживаемое вложение (по
   ``mail_attachment_filter`` или просто первое с известным расширением),
   помечаем ``\\Seen``, возвращаем :class:`AttachmentCandidate`.

Idempotency: дедуп по ``Message-ID`` происходит в :mod:`importer` (через
``erp_sync_runs.message_id`` UNIQUE), а не здесь — mailbox только фетчит.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from email import message_from_bytes
from email.utils import getaddresses
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.services.erp_sync.parser import SUPPORTED_FORMATS, detect_format

if TYPE_CHECKING:
    from app.schemas.branding import EmailSettings

logger = get_logger(__name__)

# Redis-ключи для interval-guard и distributed-lock (клон helpdesk-конвенции).
LAST_POLL_KEY = "erp_sync:imap:last_poll_at"
POLL_LOCK_KEY = "erp_sync:imap:poll_lock"
POLL_LOCK_TTL = 300  # 5 минут — хватает на обработку нескольких писем.
LAST_SUCCESS_KEY = "erp_sync:last_success_at"  # для watchdog + health-probe.

# Таймауты на IMAP-операции (секунды). 15 c на handshake/login (российские
# хосты бывают медленные), как в helpdesk.
_IMAP_STEP_TIMEOUT = 15.0

# Маркер «aioimaplib возвращает плоский список с literal-маркером».
_LITERAL_RE = re.compile(rb"\{\d+\}")


@dataclass
class AttachmentCandidate:
    """Вложение из подходящего письма, готовое к импорту."""

    filename: str
    data: bytes
    message_id: str | None


@dataclass
class MailFilters:
    """Per-module фильтры писем (ADR-048): IMAP-ящик общий, фильтры — у модуля.

    Пустое значение = ограничение не накладывается (любое значение проходит).
    Все заданные фильтры должны совпасть (AND).
    """

    subject_filter: str | None = None
    sender_filter: str | None = None
    attachment_filter: str | None = None


def _make_imap_client_raw(*, host: str, port: int, use_ssl: bool) -> Any:
    """Создать aioimaplib-клиент (без подключения)."""
    import aioimaplib

    if use_ssl:
        return aioimaplib.IMAP4_SSL(host=host, port=port)
    return aioimaplib.IMAP4(host=host, port=port)


# ── Декодирование заголовков (переиспользуем helpdesk-threading) ────────────


def _decode_mime_header(raw: str | None) -> str:
    """Декодировать RFC 2047 encoded-words (=?UTF-8?B?...?=).

    Переиспользует ту же логику, что helpdesk — ``email.header.decode_header``
    + ``make_header`` (не ручной base64).
    """
    if not raw:
        return ""
    try:
        from email.header import decode_header, make_header

        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _extract_sender_email(msg: Any) -> str:
    """Email отправителя (lowercase) или '' — для фильтра ``mail_sender_filter``."""
    from_addrs = [a.lower() for _n, a in getaddresses(msg.get_all("From", []))]
    return from_addrs[0] if from_addrs else ""


# ── Фильтрация писем ────────────────────────────────────────────────────────


def _matches_filters(
    msg: Any,
    *,
    subject_filter: str | None,
    sender_filter: str | None,
) -> bool:
    """Подходит ли письмо под фильтры (CI-подстрока).

    Пустой фильтр = ограничение не накладывается (любое значение проходит).
    Все заданные фильтры должны совпасть (AND).
    """
    subject = _decode_mime_header(msg.get("Subject"))
    sender = _extract_sender_email(msg)
    subject_ok = not subject_filter or subject_filter.lower() in subject.lower()
    sender_ok = not sender_filter or sender_filter.lower() in sender
    return subject_ok and sender_ok


def _pick_attachment(msg: Any, *, attachment_filter: str | None) -> tuple[str, bytes] | None:
    """Извлечь подходящее вложение из MIME-дерева письма.

    Возвращает ``(filename, data)`` или ``None``, если подходящего нет.

    Логика выбора:

    * Если задан ``attachment_filter`` — берём первое вложение, чьё имя
      содержит подстроку (CI). Защищает от писем с несколькими файлами.
    * Иначе — первое вложение с поддерживаемым расширением
      (через :func:`detect_format`).
    """
    for part in msg.walk():
        disp = (part.get_content_disposition() or "").lower()
        if disp != "attachment":
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            continue
        raw_name = part.get_filename() or "attachment"
        name = _decode_mime_header(raw_name) or "attachment"
        if attachment_filter:
            if attachment_filter.lower() in name.lower():
                return name, bytes(payload)
            continue
        # Без явного фильтра — только поддерживаемые форматы.
        if detect_format(name) in SUPPORTED_FORMATS:
            return name, bytes(payload)
    return None


# ── Извлечение RFC822 из aioimaplib-ответа ──────────────────────────────────


def _extract_rfc822(data: Any) -> bytes | None:
    """Извлечь raw RFC822 из aioimaplib fetch-ответа.

    aioimaplib возвращает плоский список, где тело идёт сразу за literal-
    маркером ``{NNN}``. Клон helpdesk-паттерна (там это было граблей: tuple-
    поиск молча возвращал None → все письма падали в errors).
    """
    items = list(data)
    for i, item in enumerate(items):
        if isinstance(item, (bytes, bytearray)) and b"{" in item and b"}" in item:
            preview = bytes(item)
            if _LITERAL_RE.search(preview) and i + 1 < len(items):
                body = items[i + 1]
                if isinstance(body, (bytes, bytearray)):
                    return bytes(body)
    for item in items:
        if isinstance(item, tuple):
            for part in item:
                if isinstance(part, (bytes, bytearray)) and not _LITERAL_RE.search(bytes(part)):
                    return bytes(part)
    return None


def _extract_message_id(msg: Any) -> str | None:
    """Message-ID письма (нормализованный) или None."""
    raw = msg.get("Message-ID") or msg.get("Message-Id")
    if not raw:
        return None
    token = raw.strip().split()[0] if raw.strip() else ""
    return token or None


async def _safe_seen(client: Any, uid: str) -> None:
    """Пометить письмо ``\\Seen`` (best-effort)."""
    try:
        await client.store(uid, "+FLAGS", "\\Seen")
    except Exception:
        logger.warning("erp_sync.mailbox.mark_seen_failed", uid=uid, exc_info=True)


async def _search_unseen(client: Any) -> list[str]:
    """Поиск непрочитанных писем (``SEARCH UNSEEN``)."""
    typ, data = await client.search("UNSEEN")
    if typ != "OK" or not data or not data[0]:
        return []
    raw = data[0]
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="ignore")
    return [u for u in raw.split() if u]


async def fetch_unread_attachments(
    email_settings: EmailSettings,
    filters: MailFilters,
) -> list[tuple[AttachmentCandidate, str]]:
    """Опросить общий IMAP-ящик, вернуть вложения, подходящие под фильтры модуля.

    IMAP-настройки (host/port/ssl/username/password/folder) — общие, из
    ``EmailSettings`` (ADR-048). Фильтры писём — per-module (``filters``).

    Возвращает список ``(candidate, uid)``. Каждое подходящее письмо
    помечается ``\\Seen``; письма мимо фильтра **не** трогаются.

    Не делает дедуп по Message-ID (это забота importer) и не пишет в БД —
    только IMAP. Вызывающий код (worker) пробегает по результатам и вызывает
    :func:`run_import` для каждого.
    """
    password = email_settings.imap_password
    if not password:
        logger.warning("erp_sync.mailbox.no_password")
        return []

    client = _make_imap_client_raw(
        host=email_settings.imap_host,
        port=email_settings.imap_port,
        use_ssl=email_settings.imap_use_ssl,
    )
    results: list[tuple[AttachmentCandidate, str]] = []
    try:
        await asyncio.wait_for(client.wait_hello_from_server(), timeout=_IMAP_STEP_TIMEOUT)
        await asyncio.wait_for(
            client.login(email_settings.imap_username, password), timeout=_IMAP_STEP_TIMEOUT
        )
        await client.select(email_settings.imap_folder)

        uids = await _search_unseen(client)
        for uid in uids:
            try:
                candidate = await _process_uid(client, uid, filters=filters)
                if candidate is not None:
                    results.append((candidate, uid))
            except Exception:
                logger.exception("erp_sync.mailbox.uid_failed", uid=uid)
                # Не помечаем Seen при ошибке — пусть повторится в следующий poll.
    finally:
        try:
            await client.logout()
        except Exception:
            logger.warning("erp_sync.mailbox.logout_failed", exc_info=True)

    logger.info("erp_sync.mailbox.poll_done", fetched=len(uids), matched=len(results))
    return results


async def _process_uid(
    client: Any, uid: str, *, filters: MailFilters
) -> AttachmentCandidate | None:
    """Обработать одно письмо: фетч → фильтр → вложение → ``\\Seen``."""
    typ, data = await client.fetch(uid, "(RFC822)")
    if typ != "OK":
        return None
    raw = _extract_rfc822(data)
    if raw is None:
        logger.warning("erp_sync.mailbox.no_rfc822", uid=uid)
        return None
    msg = message_from_bytes(raw)

    # 1. Фильтрация. Письмо мимо фильтра → пропускаем, НЕ помечаем Seen.
    if not _matches_filters(
        msg,
        subject_filter=filters.subject_filter,
        sender_filter=filters.sender_filter,
    ):
        logger.debug("erp_sync.mailbox.filtered_out", uid=uid)
        return None

    # 2. Вложение.
    picked = _pick_attachment(msg, attachment_filter=filters.attachment_filter)
    if picked is None:
        logger.info("erp_sync.mailbox.no_suitable_attachment", uid=uid)
        # Подошло по фильтру, но нет вложения — помечаем Seen, чтобы не
        # крутить одно и то же письмо бесконечно (это всё-таки «наше» письмо).
        await _safe_seen(client, uid)
        return None

    filename, filedata = picked
    # 3. Пометить Seen только для действительно обработанного письма.
    await _safe_seen(client, uid)

    return AttachmentCandidate(
        filename=filename,
        data=filedata,
        message_id=_extract_message_id(msg),
    )


async def probe_imap_connection(
    *, host: str, port: int, username: str, password: str, use_ssl: bool, folder: str
) -> tuple[bool, str]:
    """Лёгкая проверка подключения (login + select). Для ``POST /erp-sync/test``.

    Возвращает ``(ok, detail)``. ``detail`` может содержать тип исключения —
    вызывающий код (API endpoint) обязан маскировать его, т.к. aioimaplib в
    некоторых исключениях echo'ит LOGIN-команду с паролем (грабля H-9).
    """
    try:
        client = _make_imap_client_raw(host=host, port=port, use_ssl=use_ssl)
        await asyncio.wait_for(client.wait_hello_from_server(), timeout=10)
        await asyncio.wait_for(client.login(username, password), timeout=10)
        resp = await client.select(folder)
        ok = bool(resp and "OK" in resp[0])
        await client.logout()
        if ok:
            return True, f"Подключено, выбрана папка «{folder}»"
        return False, f"select failed: {resp}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
