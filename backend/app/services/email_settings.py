"""Email (SMTP + общий IMAP) settings storage + test helpers.

Extracted from ``app.api.branding``. Persists config to
``/data/branding/email-settings.json`` in a format cross-read by
``app.worker.tasks.email_utils.load_smtp_config`` and the meetings notifier,
so the on-disk schema must stay compatible.

IMAP-блок (ADR-048) — общий приёмник почты портала. В отличие от SMTP-пароля
(plaintext), IMAP-пароль хранится **Fernet-шифром** (поле ``imap_password_enc``
на диске), в модели ``EmailSettings.imap_password`` — plaintext (для удобства
использования модулями). Шифрование/дешифрование — только здесь, в этом модуле.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.core.secret_crypto import decrypt_secret, encrypt_secret
from app.schemas.branding import EmailSettings, EmailSettingsOut

logger = get_logger(__name__)

BRANDING_DIR = Path("/data/branding")
EMAIL_SETTINGS_FILE = BRANDING_DIR / "email-settings.json"
EMAIL_PASSWORD_MASK = "***"

# In-process TTL-кеш для email-settings (audit [H4], 2026-08-09). Файл читается
# на каждом тике worker'ов (`load_smtp_config`, meetings-нотификатор, erp_sync)
# и на admin-путях — без кеша это sync disk-read + JSON-parse + Fernet-decrypt
# каждый раз. Кеш снимает I/O до cache-miss раз в _CACHE_TTL секунд на процесс.
# Cross-process задержка после admin-save ≤ TTL (приемлемо для SMTP/IMAP).
# `save_email_settings()` инвалидирует кеш в текущем процессе. Deep-copy при
# возврате — потребители не должны мутировать кешированный объект.
_CACHE_TTL = 60
_cache: dict[str, Any] = {}


def _settings_from_disk(data: dict) -> EmailSettings:
    """Распарсить on-disk dict в ``EmailSettings``, расшифровав IMAP-пароль.

    На диске IMAP-пароль лежит как ``imap_password_enc`` (Fernet-шифр) —
    расшифровываем в ``imap_password`` (plaintext) для потребителей. Если шифра
    нет — пусто. SMTP-пароль хранится plaintext и читается как есть.
    """
    enc = data.get("imap_password_enc")
    imap_password = ""
    if enc:
        try:
            imap_password = decrypt_secret(enc)
        except Exception:
            logger.exception("email_settings.imap_password_decrypt_failed")
    # Убираем служебное on-disk поле, кладём plaintext в модельное поле.
    payload = {k: v for k, v in data.items() if k != "imap_password_enc"}
    payload["imap_password"] = imap_password
    return EmailSettings.model_validate(payload)


def _settings_to_disk(s: EmailSettings) -> dict:
    """Сериализовать ``EmailSettings`` в on-disk dict, зашифровав IMAP-пароль.

    IMAP-пароль → ``imap_password_enc`` (Fernet). ``imap_password`` (plaintext)
    на диск НЕ пишем. SMTP-пароль остаётся plaintext (намеренно, ADR-048).
    """
    data: dict = json.loads(s.model_dump_json())
    if data.get("imap_password"):
        data["imap_password_enc"] = encrypt_secret(data.pop("imap_password"))
    else:
        data.pop("imap_password", None)
    return data


def _read_from_disk() -> EmailSettings | None:
    """Read+parse email-settings.json from disk (no cache). Returns None if absent/invalid.

    Это единственное место, читающее и парсящее файл напрямую. Публичный
    ``read_email_settings()`` оборачивает его в TTL-кеш.
    """
    if EMAIL_SETTINGS_FILE.exists():
        try:
            data = json.loads(EMAIL_SETTINGS_FILE.read_text("utf-8"))
            return _settings_from_disk(data)
        except Exception:
            logger.exception("email_settings.load_failed")
    return None


def read_email_settings() -> EmailSettings | None:
    """Единый загрузчик on-disk ``email-settings.json`` (TTL-кешируется, audit [H4]).

    Возвращает deep-copy разобранных настроек либо ``None``, если файл
    отсутствует/не читается/не валиден. Потребители (worker ``load_smtp_config``,
    meetings-нотификатор, erp_sync) делегируют сюда, чтобы on-disk схема была
    определена в одном месте. Cache-miss раз в ``_CACHE_TTL`` секунд на процесс;
    ``save_email_settings()`` инвалидирует кеш немедленно в текущем процессе.
    """
    now = time.monotonic()
    if "data" not in _cache or now - _cache.get("fetched_at", 0.0) >= _CACHE_TTL:
        # None тоже кешируем (файл отсутствует) — иначе каждый тик worker'а
        # будет стучать на диск в ожидании настройки.
        _cache["data"] = _read_from_disk()
        _cache["fetched_at"] = now
    # Возвращаем deep-copy — мутирующие потребители не должны портить кеш.
    snapshot = copy.deepcopy(_cache["data"])
    return snapshot if isinstance(snapshot, (EmailSettings, type(None))) else None


def invalidate_email_settings_cache() -> None:
    """Drop in-process cache (called after ``save_email_settings``)."""
    _cache.clear()


def load_email_settings() -> EmailSettings:
    return read_email_settings() or EmailSettings()


def save_email_settings(s: EmailSettings) -> None:
    from app.core.system_config import atomic_write

    # email-settings.json содержит SMTP-пароль (plaintext) и IMAP-шифр → 0o600.
    atomic_write(
        EMAIL_SETTINGS_FILE,
        json.dumps(_settings_to_disk(s), indent=2, ensure_ascii=False),
        mode=0o600,
    )
    invalidate_email_settings_cache()


def email_settings_to_out(s: EmailSettings) -> EmailSettingsOut:
    return EmailSettingsOut(
        host=s.host,
        port=s.port,
        from_address=s.from_address,
        from_name=s.from_name,
        username=s.username,
        password_set=bool(s.password),
        use_tls=s.use_tls,
        use_starttls=s.use_starttls,
        imap_host=s.imap_host,
        imap_port=s.imap_port,
        imap_use_ssl=s.imap_use_ssl,
        imap_username=s.imap_username,
        imap_password_set=bool(s.imap_password),
        imap_folder=s.imap_folder,
    )


def imap_configured(s: EmailSettings) -> bool:
    """Достаточно ли настроен общий IMAP для подключения (host + username + пароль)."""
    return bool(s.imap_host and s.imap_username and s.imap_password)


def format_email_from(from_name: str, from_address: str) -> str:
    """``From``-заголовок с display name: ``Имя <addr>`` либо голый ``addr``.

    ``formataddr`` корректно экранирует спецсимволы в имени (RFC 5322).
    Пустое имя → без изменения текущего поведения.
    """
    from email.utils import formataddr

    addr = from_address or "portal@company.local"
    name = (from_name or "").strip()
    return formataddr((name, addr)) if name else addr


async def send_test_email(settings: EmailSettings, to: str, sender_name: str) -> None:
    try:
        import html as _html
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        import aiosmtplib

        sender_esc = _html.escape(sender_name or "", quote=True)
        host_esc = _html.escape(settings.host or "", quote=True)
        subject = "Тестовое письмо от Корпоративного портала"
        html = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Тест</title></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0">
  <table width="600" align="center" style="background:#fff;border-radius:8px;margin:32px auto;padding:32px">
    <tr><td>
      <h2 style="color:#143a66;margin:0 0 16px">Корпоративный портал</h2>
      <p style="font-size:16px;color:#333">Это тестовое письмо отправлено администратором <strong>{sender_esc}</strong>.</p>
      <p style="font-size:14px;color:#666">Если вы получили это письмо — настройки SMTP работают корректно.</p>
      <p style="margin-top:24px;font-size:12px;color:#999">Сервер: {host_esc}:{settings.port}</p>
    </td></tr>
  </table>
</body>
</html>"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = format_email_from(settings.from_name, settings.from_address)
        msg["To"] = to
        msg.attach(
            MIMEText(
                "Тестовое письмо от Корпоративного портала. SMTP работает корректно.",
                "plain",
                "utf-8",
            )
        )
        msg.attach(MIMEText(html, "html", "utf-8"))

        smtp_kwargs: dict = {"hostname": settings.host, "port": settings.port}
        if settings.use_tls:
            smtp_kwargs["use_tls"] = True
        if settings.use_starttls:
            smtp_kwargs["start_tls"] = True
        if settings.username and settings.password:
            smtp_kwargs["username"] = settings.username
            smtp_kwargs["password"] = settings.password

        await aiosmtplib.send(msg, **smtp_kwargs)
        logger.info("branding.test_email_sent", to=to)
    except Exception as exc:
        logger.exception(
            "branding.test_email_failed", error=str(exc), error_type=type(exc).__name__, to=to
        )


async def test_imap_connection(settings: EmailSettings) -> tuple[bool, str]:
    """Проверка общего IMAP-ящика (login + select folder). Для ``POST imap/test``.

    Переиспользует ``probe_imap_connection`` из erp_sync (тот же aioimaplib-зонд).
    Локальный импорт — чтобы не тащить цикл ``email_settings ↔ erp_sync.mailbox``
    на уровне модуля (mailbox сам читает настройки через этот модуль).
    """
    if not imap_configured(settings):
        return False, "IMAP не настроен (host/username/password)"

    from app.services.erp_sync.mailbox import probe_imap_connection

    return await probe_imap_connection(
        host=settings.imap_host,
        port=settings.imap_port,
        username=settings.imap_username,
        password=settings.imap_password,
        use_ssl=settings.imap_use_ssl,
        folder=settings.imap_folder,
    )
