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
    *, news_title: str, excerpt: str, news_link: str, portal_name: str = _PORTAL_NAME
) -> tuple[str, str]:
    """Build (html, text) bodies for the share email."""
    title_esc = _esc(news_title)
    portal_esc = _esc(portal_name)
    link_esc = _esc(news_link)
    excerpt_html = _esc(excerpt).replace("\n", "<br>")
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Новость</title></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0">
  <table width="600" align="center" style="background:#fff;border-radius:8px;margin:32px auto;padding:32px">
    <tr><td>
      <h2 style="color:#143a66;margin:0 0 16px">{portal_esc}</h2>
      <h3 style="color:#1d4e89;margin:0 0 12px">{title_esc}</h3>
      <p style="font-size:15px;color:#333;line-height:1.6">{excerpt_html}</p>
      <a href="{link_esc}" style="display:inline-block;margin-top:16px;padding:10px 20px;background:#d8262c;color:#fff;border-radius:4px;text-decoration:none">
        Читать новость
      </a>
    </td></tr>
  </table>
</body>
</html>"""
    text = f"{portal_name}\n\n{news_title}\n\n{excerpt}\n\n{news_link}"
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
        news_title=news.title, excerpt=excerpt, news_link=news_link
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
