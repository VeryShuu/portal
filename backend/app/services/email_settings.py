"""Email (SMTP) settings storage + test-email sender.

Extracted from ``app.api.branding``. Persists SMTP config to
``/data/branding/email-settings.json`` in a format cross-read by
``app.worker.tasks.email_utils.load_smtp_config`` and the meetings notifier,
so the on-disk schema must stay compatible.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from app.core.logging import get_logger
from app.schemas.branding import EmailSettings, EmailSettingsOut

logger = get_logger(__name__)

BRANDING_DIR = Path("/data/branding")
EMAIL_SETTINGS_FILE = BRANDING_DIR / "email-settings.json"
EMAIL_PASSWORD_MASK = "***"


def read_email_settings() -> EmailSettings | None:
    """Единый загрузчик on-disk ``email-settings.json``.

    Единственное место, читающее и парсящее файл. Возвращает разобранные
    настройки либо ``None``, если файл отсутствует/не читается/не валиден.
    Потребители (worker ``load_smtp_config``, meetings-нотификатор) делегируют
    сюда, чтобы on-disk схема была определена в одном месте и не разъехалась.
    """
    if EMAIL_SETTINGS_FILE.exists():
        try:
            return EmailSettings.model_validate_json(EMAIL_SETTINGS_FILE.read_text("utf-8"))
        except Exception:
            logger.exception("email_settings.load_failed")
    return None


def load_email_settings() -> EmailSettings:
    return read_email_settings() or EmailSettings()


def save_email_settings(s: EmailSettings) -> None:
    from app.core.system_config import atomic_write

    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(EMAIL_SETTINGS_FILE, s.model_dump_json(indent=2))
    # email-settings.json содержит SMTP-пароль.
    with contextlib.suppress(OSError):
        os.chmod(EMAIL_SETTINGS_FILE, 0o600)


def email_settings_to_out(s: EmailSettings) -> EmailSettingsOut:
    return EmailSettingsOut(
        host=s.host,
        port=s.port,
        from_address=s.from_address,
        username=s.username,
        password_set=bool(s.password),
        use_tls=s.use_tls,
        use_starttls=s.use_starttls,
    )


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
        msg["From"] = settings.from_address or "portal@company.local"
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
