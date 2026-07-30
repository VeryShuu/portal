"""Общие хелперы отправки email: SMTP-конфиг, классификация ошибок, backoff."""

from __future__ import annotations

import random
from email.message import Message
from typing import Literal

import aiosmtplib

from app.core.logging import get_logger

logger = get_logger(__name__)

ErrorClass = Literal["transient", "permanent", "unknown"]

JOB_TIMEOUT_SECONDS = 60
MAX_TRIES = 6
OUTBOX_MAX_ATTEMPTS = 6
SMTP_TIMEOUT_SECONDS = 30

_TRANSIENT_TYPES = {
    "SMTPConnectError",
    "SMTPConnectTimeoutError",
    "SMTPServerDisconnected",
    "SMTPHeloError",
    "SMTPTimeoutError",
    "TimeoutError",
    "ConnectionError",
    "ConnectionRefusedError",
    "ConnectionResetError",
    "OSError",
    "SMTPNotSupported",
}

_PERMANENT_TYPES = {
    "SMTPAuthenticationError",
    "SMTPRecipientsRefused",
    "SMTPSenderRefused",
    "SMTPDataError",
}


def load_smtp_config() -> dict:
    """Читает SMTP-настройки из email-settings.json через единый загрузчик."""
    from app.services.email_settings import read_email_settings

    s = read_email_settings()
    if s is None:
        return {
            "host": "",
            "port": 25,
            "from_address": "portal@company.local",
            "username": "",
            "password": "",
            "use_tls": False,
            "use_starttls": False,
        }
    return {
        "host": s.host,
        "port": s.port,
        "from_address": s.from_address,
        "username": s.username,
        "password": s.password,
        "use_tls": s.use_tls,
        "use_starttls": s.use_starttls,
    }


async def load_helpdesk_smtp_config() -> dict | None:
    """SMTP-конфиг собственного исходящего контура helpdesk (миграция 086).

    Читает singleton ``helpdesk_mailbox_settings`` (``id=1``), расшифровывает
    ``smtp_password_enc`` и возвращает cfg-dict в том же формате, что
    :func:`load_smtp_config`, но с ``from_address = support_address`` — чтобы
    ``From:``, envelope MAIL FROM (автоматически из ``From:``) и SMTP-логин были
    консистентны с адресом приёма заявок.

    Возвращает ``None`` (→ fallback на общий порталный SMTP), если:

    * singleton-строка ещё не создана (mailbox не настроен);
    * ``smtp_host`` пуст/None (админ не заполнил SMTP-блок — осознанный fallback);
    * ``smtp_password_enc`` пуст (без пароля login не состоится; для безauth-релея
      админ заполняет host, а пароль оставляет пустым — этот кейс тут не покрыт
      сознательно: helpdesk-исходящая почта важна, и мы требуем явные креды).

    Воркер (``process_email_outbox``) вызывает это **один раз на batch** (рядом с
    ``load_smtp_config``) и роутит helpdesk-строки на возвращённый cfg.
    """
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.core.secret_crypto import decrypt_secret
    from app.models.helpdesk import HelpdeskMailboxSettings

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(HelpdeskMailboxSettings).where(HelpdeskMailboxSettings.id == 1)
        )
        row = res.scalars().one_or_none()
    if row is None:
        return None
    host = (row.smtp_host or "").strip()
    if not host or not row.smtp_password_enc:
        return None
    return {
        "host": host,
        "port": row.smtp_port,
        # from_address = support_address: From: и Reply-To: для всей helpdesk-почты
        # совпадают с адресом приёма. _resolve_helpdesk_reply_to использует payload
        # support_address, но cfg.from_address задаёт именно заголовок From:.
        "from_address": row.support_address,
        "username": row.smtp_username or "",
        "password": decrypt_secret(row.smtp_password_enc),
        "use_tls": row.smtp_use_tls,
        "use_starttls": row.smtp_use_starttls,
    }


def build_smtp_kwargs(cfg: dict) -> dict:
    smtp_kwargs: dict = {
        "hostname": cfg["host"],
        "port": cfg["port"],
        "timeout": SMTP_TIMEOUT_SECONDS,
    }
    if cfg.get("use_tls"):
        smtp_kwargs["use_tls"] = True
    if cfg.get("use_starttls"):
        smtp_kwargs["start_tls"] = True
    if cfg.get("username") and cfg.get("password"):
        smtp_kwargs["username"] = cfg["username"]
        smtp_kwargs["password"] = cfg["password"]
    return smtp_kwargs


def classify_smtp_error(exc: BaseException) -> ErrorClass:
    """Определяет, имеет ли смысл повторять отправку.

    transient — сетевые / временные проблемы → retry
    permanent — auth / refused / 5xx → не retry, сразу финальный fail
    unknown   — всё прочее → retry с осторожным backoff
    """
    name = type(exc).__name__

    if isinstance(exc, aiosmtplib.SMTPResponseException):
        code = getattr(exc, "code", 0) or 0
        if 400 <= code < 500:
            return "transient"
        if 500 <= code < 600:
            return "permanent"

    if name in _PERMANENT_TYPES:
        return "permanent"
    if name in _TRANSIENT_TYPES:
        return "transient"

    return "unknown"


def compute_retry_defer(job_try: int, error_class: ErrorClass) -> int:
    """Экспоненциальный backoff с джиттером.

    transient: 30, 60, 120, 240, 480, 960 с
    unknown:   15, 30, 60, 120, 240, 480 с
    permanent: 0 (не должен вызываться — сразу fail)
    """
    if error_class == "permanent":
        return 0
    base = 30 if error_class == "transient" else 15
    attempt = max(1, job_try)
    delay = base * (2 ** (attempt - 1))
    delay = min(delay, 1800)
    jitter = random.uniform(0, delay * 0.15)
    return int(delay + jitter)


async def smtp_send(msg: Message, cfg: dict | None = None) -> None:
    """Тонкая обёртка над aiosmtplib.send с готовыми kwargs."""
    cfg = cfg or load_smtp_config()
    await aiosmtplib.send(msg, **build_smtp_kwargs(cfg))
