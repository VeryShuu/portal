"""Общие хелперы отправки email: SMTP-конфиг, классификация ошибок, backoff."""

from __future__ import annotations

import json
import random
from email.message import Message
from pathlib import Path
from typing import Literal

import aiosmtplib

from app.core.logging import get_logger

logger = get_logger(__name__)

ErrorClass = Literal["transient", "permanent", "unknown"]

EMAIL_SETTINGS_PATH = Path("/data/branding/email-settings.json")

JOB_TIMEOUT_SECONDS = 60
MAX_TRIES = 6
OUTBOX_MAX_ATTEMPTS = 6

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
    """Читает SMTP-настройки из /data/branding/email-settings.json."""
    if EMAIL_SETTINGS_PATH.exists():
        try:
            data = json.loads(EMAIL_SETTINGS_PATH.read_text("utf-8"))
            return {
                "host": data.get("host", ""),
                "port": int(data.get("port", 25)),
                "from_address": data.get("from_address", ""),
                "username": data.get("username", ""),
                "password": data.get("password", ""),
                "use_tls": bool(data.get("use_tls", False)),
                "use_starttls": bool(data.get("use_starttls", False)),
            }
        except Exception as exc:
            logger.warning("email_utils.smtp_config_load_failed", error=str(exc))
    return {
        "host": "",
        "port": 25,
        "from_address": "portal@company.local",
        "username": "",
        "password": "",
        "use_tls": False,
        "use_starttls": False,
    }


def build_smtp_kwargs(cfg: dict) -> dict:
    smtp_kwargs: dict = {
        "hostname": cfg["host"],
        "port": cfg["port"],
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
