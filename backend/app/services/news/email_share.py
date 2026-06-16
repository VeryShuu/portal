"""Ad-hoc "share news by email" flow (docs/wip/news-email-share.md).

An editor picks recipients from the mailing recipients directory and sends them
a short email about a *published* news item. Delivery goes through the
transactional outbox (``enqueue_outbox_email``) — no SMTP code here. The caller
(API route) owns the transaction and must ``commit`` so the outbox rows land
atomically with the business operation.
"""

from __future__ import annotations

import html as _html
import re
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.system_config import load_system_settings
from app.models.mailing_recipient import MailingRecipient
from app.models.news import News as NewsModel
from app.models.user import User
from app.services.email_outbox import KIND_NEWS, enqueue_outbox_email

logger = get_logger(__name__)

_PORTAL_NAME = "Корпоративный портал"
_EXCERPT_LIMIT = 300

# Lightweight Markdown → plain-text stripping for the auto-generated excerpt.
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_MD_INLINE_TOKENS_RE = re.compile(r"[`*_~>#]+")
_WS_RE = re.compile(r"\s+")


def _esc(value: str | None) -> str:
    """HTML-escape for safe interpolation into the email template."""
    return _html.escape(value or "", quote=True)


def build_news_excerpt(body: str | None, *, limit: int = _EXCERPT_LIMIT) -> str:
    """Derive a short plain-text excerpt from a Markdown news body."""
    text = body or ""
    text = _MD_CODE_FENCE_RE.sub(" ", text)
    text = _MD_IMAGE_RE.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_INLINE_TOKENS_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def build_share_email_content(
    *,
    news_title: str,
    excerpt: str,
    news_link: str,
    portal_url: str = "",
    portal_name: str = _PORTAL_NAME,
) -> tuple[str, str]:
    """Build (html, text) bodies for the share email."""
    title_esc = _esc(news_title)
    portal_esc = _esc(portal_name)
    link_esc = _esc(news_link)
    portal_url_esc = _esc(portal_url)
    excerpt_html = _esc(excerpt).replace("\n", "<br>")

    portal_link_html = ""
    portal_link_text = ""
    if portal_url:
        portal_link_html = (
            f'<p style="font-size:13px;color:#5b6470;margin:0 0 10px;line-height:1.6">'
            f"Открыть портал: "
            f'<a href="{portal_url_esc}" style="color:#1d4e89;text-decoration:underline">'
            f"{portal_url_esc}</a></p>"
        )
        portal_link_text = f"\nОткрыть портал: {portal_url}"

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light only">
  <meta name="supported-color-schemes" content="light">
  <title>Новость</title>
</head>
<body style="margin:0;padding:0;background:#eef0f4;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#2b2f36">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef0f4">
    <tr><td align="center" style="padding:32px 16px">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(20,58,102,0.08)">
        <tr>
          <td style="background:#143a66;padding:20px 32px">
            <span style="font-size:17px;font-weight:bold;color:#fffffe;letter-spacing:.02em">{portal_esc}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:32px">
            <p style="font-size:12px;color:#8a93a0;margin:0 0 14px;text-transform:uppercase;letter-spacing:.06em">
              Новость на корпоративном портале
            </p>
            <h1 style="font-size:22px;line-height:1.3;color:#143a66;margin:0 0 16px;font-weight:bold">{title_esc}</h1>
            <p style="font-size:15px;color:#3d434c;line-height:1.65;margin:0 0 28px">{excerpt_html}</p>
            <table role="presentation" cellpadding="0" cellspacing="0">
              <tr>
                <td bgcolor="#d8262c" style="background:#d8262c;border-radius:6px">
                  <a href="{link_esc}" style="display:inline-block;padding:13px 30px;font-size:15px;font-weight:bold;color:#fffffe !important;text-decoration:none;border-radius:6px">Читать новость &rarr;</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="background:#f5f6f8;padding:20px 32px;border-top:1px solid #e6e8ec">
            {portal_link_html}
            <p style="font-size:13px;color:#5b6470;margin:0 0 10px;line-height:1.6">
              Доступ к порталу возможен только из офиса или через корпоративный VPN.
            </p>
            <p style="font-size:12px;color:#9aa2ad;margin:0;line-height:1.6">
              Это автоматическое уведомление, отвечать на него не нужно.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    text = (
        f"{portal_name}\n"
        f"Новость на корпоративном портале\n\n"
        f"{news_title}\n\n{excerpt}\n\n"
        f"Читать новость: {news_link}{portal_link_text}\n\n"
        f"Доступ к порталу возможен только из офиса или через корпоративный VPN.\n"
        f"Это автоматическое уведомление, отвечать на него не нужно."
    )
    return html, text


async def share_news_by_email(
    session: AsyncSession,
    *,
    news: NewsModel,
    recipients: Sequence[MailingRecipient],
    message: str | None,
    actor: User,
) -> int:
    """Enqueue one outbox row per recipient. Caller must commit.

    Returns the number of successfully enqueued emails. Each recipient is
    isolated in a SAVEPOINT (``begin_nested``) so a single failing INSERT does
    not abort the whole batch (see E5 note in worker notifications).
    """
    base = (load_system_settings().portal_base_url or "").rstrip("/")
    news_link = f"{base}/news/{news.id}"
    excerpt = (message or "").strip() or build_news_excerpt(news.body)
    html, text = build_share_email_content(
        news_title=news.title, excerpt=excerpt, news_link=news_link, portal_url=base
    )
    subject = f"Новость: {news.title}"
    news_id: uuid.UUID = news.id

    enqueued = 0
    for recipient in recipients:
        try:
            async with session.begin_nested():
                await enqueue_outbox_email(
                    session,
                    kind=KIND_NEWS,
                    to_email=recipient.email,
                    subject=subject,
                    body_html=html,
                    body_text=text,
                    related_resource_type="news",
                    related_resource_id=news_id,
                    created_by_user_id=actor.id,
                )
            enqueued += 1
        except Exception as exc:
            logger.exception(
                "news.share_email_enqueue_failed",
                news_id=str(news_id),
                to=recipient.email,
                error=str(exc),
            )
    return enqueued
