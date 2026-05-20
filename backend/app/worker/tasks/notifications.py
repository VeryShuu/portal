"""ARQ задачи для уведомлений: отправка email, триггеры по событиям."""

from __future__ import annotations

import html as _html

from arq import Retry

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.system_config import load_system_settings
from app.worker.tasks.email_utils import (
    JOB_TIMEOUT_SECONDS,
    MAX_TRIES,
    classify_smtp_error,
    compute_retry_defer,
    load_smtp_config,
    smtp_send,
)


def _esc(value: str | None) -> str:
    """HTML-escape для безопасной интерполяции в email-шаблоны.

    Защищает от HTML/script-инъекций через заголовок новости/статьи.
    Для ссылок дополнительно экранирует кавычки (quote=True).
    """
    return _html.escape(value or "", quote=True)


logger = get_logger(__name__)
settings = get_settings()


async def send_email_notification(
    ctx: dict,
    *,
    to_email: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
) -> bool:
    """Отправляет email через aiosmtplib с управляемым retry через ARQ."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    cfg = load_smtp_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_address"] or "portal@company.local"
    msg["To"] = to_email

    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    job_try = int(ctx.get("job_try") or 1)

    try:
        await smtp_send(msg, cfg)
        logger.info("email.sent", to=to_email, subject=subject)
        return True
    except Exception as exc:
        error_class = classify_smtp_error(exc)
        error_type = type(exc).__name__
        logger.exception(
            "email.send_failed",
            error=str(exc),
            error_type=error_type,
            error_class=error_class,
            job_try=job_try,
            to=to_email,
        )
        if error_class == "permanent" or job_try >= MAX_TRIES:
            raise
        defer = compute_retry_defer(job_try, error_class)
        raise Retry(defer=defer) from exc


send_email_notification.max_tries = MAX_TRIES  # type: ignore[attr-defined]
send_email_notification.job_timeout = JOB_TIMEOUT_SECONDS  # type: ignore[attr-defined]


def _build_news_email_html(news_title: str, news_link: str, portal_name: str) -> tuple[str, str]:
    title_esc = _esc(news_title)
    portal_esc = _esc(portal_name)
    link_esc = _esc(news_link)
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Новость</title></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0">
  <table width="600" align="center" style="background:#fff;border-radius:8px;margin:32px auto;padding:32px">
    <tr><td>
      <h2 style="color:#143a66;margin:0 0 16px">{portal_esc}</h2>
      <p style="font-size:16px;color:#333">Опубликована новая новость:</p>
      <h3 style="color:#1d4e89">{title_esc}</h3>
      <a href="{link_esc}" style="display:inline-block;margin-top:16px;padding:10px 20px;background:#d8262c;color:#fff;border-radius:4px;text-decoration:none">
        Читать новость
      </a>
      <p style="margin-top:24px;font-size:12px;color:#888">
        Вы получили это письмо, так как у вас включены email-уведомления.<br>
        Управлять уведомлениями можно в настройках профиля.
      </p>
    </td></tr>
  </table>
</body>
</html>"""
    text = f"{portal_name}\n\nОпубликована новость: {news_title}\n\n{news_link}"
    return html, text


async def notify_news_published(
    ctx: dict,
    *,
    news_id: str,
    news_title: str,
    target_departments: list[str] | None = None,
    target_roles: list[str] | None = None,
) -> int:
    """Записывает email-уведомления о новой новости в outbox + триггерит in-app SSE."""
    import uuid as _uuid

    import asyncpg

    from app.core.database import AsyncSessionLocal
    from app.services.email_outbox import KIND_NEWS, enqueue_outbox_email
    from app.services.notifications import notify_users_news_published

    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)
    enqueued = 0

    try:
        rows = await conn.fetch(
            "SELECT id, email, department, role FROM users WHERE notify_email = true AND email IS NOT NULL"
        )

        news_link = f"{load_system_settings().portal_base_url}/news/{news_id}"
        portal_name = "Корпоративный портал"
        news_uuid = _uuid.UUID(news_id)

        async with AsyncSessionLocal() as session:
            async with session.begin():
                for row in rows:
                    if target_departments and row["department"] not in target_departments:
                        continue
                    if target_roles and row["role"] not in target_roles:
                        continue

                    html, text = _build_news_email_html(news_title, news_link, portal_name)
                    try:
                        await enqueue_outbox_email(
                            session,
                            kind=KIND_NEWS,
                            to_email=row["email"],
                            subject=f"Новость: {news_title}",
                            body_html=html,
                            body_text=text,
                            related_resource_type="news",
                            related_resource_id=news_uuid,
                        )
                        enqueued += 1
                    except Exception as exc:
                        logger.exception(
                            "notifications.news_enqueue_failed",
                            news_id=news_id,
                            to=row["email"],
                            error=str(exc),
                        )

    finally:
        await conn.close()

    redis = ctx.get("redis")
    if redis is not None:
        try:
            async with AsyncSessionLocal() as db:
                await notify_users_news_published(
                    db,
                    redis,
                    news_id=_uuid.UUID(news_id),
                    news_title=news_title,
                    target_departments=target_departments,
                    target_roles=target_roles,
                )
        except Exception as exc:
            logger.exception("notifications.inapp_news_failed", news_id=news_id, error=str(exc))

    logger.info("notifications.news_emails_enqueued", news_id=news_id, enqueued=enqueued)
    return enqueued


def _build_suggestion_email_html(
    article_title: str, article_link: str, action: str, portal_name: str
) -> tuple[str, str]:
    if action == "approve":
        verdict = "одобрена"
        color = "#27ae60"
    else:
        verdict = "отклонена"
        color = "#c0392b"

    title_esc = _esc(article_title)
    portal_esc = _esc(portal_name)
    link_esc = _esc(article_link)
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Правка</title></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0">
  <table width="600" align="center" style="background:#fff;border-radius:8px;margin:32px auto;padding:32px">
    <tr><td>
      <h2 style="color:#143a66;margin:0 0 16px">{portal_esc}</h2>
      <p style="font-size:16px;color:#333">Ваша правка к статье <strong>{title_esc}</strong> была рассмотрена.</p>
      <p style="font-size:18px;font-weight:bold;color:{color}">Статус: {verdict}</p>
      <a href="{link_esc}" style="display:inline-block;margin-top:16px;padding:10px 20px;background:#143a66;color:#fff;border-radius:4px;text-decoration:none">
        Перейти к статье
      </a>
    </td></tr>
  </table>
</body>
</html>"""
    text = f"{portal_name}\n\nВаша правка к статье «{article_title}» {verdict}.\n\n{article_link}"
    return html, text


async def notify_suggestion_reviewed_email(
    ctx: dict,
    *,
    author_email: str,
    article_id: str,
    article_title: str,
    action: str,
) -> bool:
    """Записывает в outbox письмо автору правки о решении (approve/reject)."""
    import uuid as _uuid

    from app.core.database import AsyncSessionLocal
    from app.services.email_outbox import KIND_KB_SUGGESTION, enqueue_outbox_email

    article_link = f"{load_system_settings().portal_base_url}/kb/articles/{article_id}"
    portal_name = "Корпоративный портал"
    html, text = _build_suggestion_email_html(article_title, article_link, action, portal_name)

    if action == "approve":
        subject = f"Ваша правка к «{article_title}» одобрена"
    else:
        subject = f"Ваша правка к «{article_title}» отклонена"

    try:
        article_uuid = _uuid.UUID(article_id)
    except (ValueError, AttributeError):
        article_uuid = None

    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await enqueue_outbox_email(
                    session,
                    kind=KIND_KB_SUGGESTION,
                    to_email=author_email,
                    subject=subject,
                    body_html=html,
                    body_text=text,
                    related_resource_type="kb_article",
                    related_resource_id=article_uuid,
                )
        return True
    except Exception as exc:
        logger.exception(
            "notifications.suggestion_enqueue_failed",
            article_id=article_id,
            to=author_email,
            error=str(exc),
        )
        return False
