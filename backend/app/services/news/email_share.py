"""Ad-hoc "share news by email" flow (docs/wip/news-email-share.md).

An editor picks recipients from the mailing recipients directory and sends them
a short email about a *published* news item. Delivery goes through the
transactional outbox (``enqueue_outbox_email``) — no SMTP code here. The caller
(API route) owns the transaction and must ``commit`` so the outbox rows land
atomically with the business operation.
"""

from __future__ import annotations

import asyncio
import base64
import html as _html
import re
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.system_config import load_system_settings
from app.models.mailing_recipient import MailingRecipient
from app.models.news import News as NewsModel
from app.models.user import User
from app.services.branding_assets import load_settings as load_branding_settings
from app.services.email_outbox import KIND_NEWS, enqueue_outbox_email

from ._helpers import _NEWS_MEDIA_DIR, build_email_cover_jpeg

logger = get_logger(__name__)

_PORTAL_NAME = "Корпоративный портал"
_DEFAULT_ACCENT = "#d8262c"
_EXCERPT_LIMIT = 300
# Cap the inline-embedded cover so a single share doesn't bloat email_outbox
# rows (the bytes are duplicated per recipient). Above it we fall back to a
# remote <img src>.
_MAX_INLINE_COVER_BYTES = 512 * 1024

# Controlled dark theme: declaring color-scheme + these overrides stops clients
# (Apple Mail, Outlook, Gmail web) from blindly inverting the palette and
# wrecking contrast (e.g. the CTA button rendering as dark text on washed-out
# red). Plain string (not an f-string) so its CSS braces survive interpolation.
_DARK_STYLE = """
    @media (prefers-color-scheme: dark) {
      body, .email-bg { background:#0f1115 !important; }
      .email-card { background:#1b1e24 !important; box-shadow:none !important; }
      .email-brand { border-color:#2a2f38 !important; }
      .email-brand-name, .email-title { color:#eef1f5 !important; }
      .email-text { color:#c4cad3 !important; }
      .email-footer { background:#15171c !important; border-color:#2a2f38 !important; }
      .email-footer a { color:#7fb0ff !important; }
      .email-muted { color:#8a93a0 !important; }
      .email-disclaimer { color:#6b7480 !important; }
    }
"""

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
    cover_url: str = "",
    cover_cid: str = "",
    accent_color: str = _DEFAULT_ACCENT,
    category: str = "",
) -> tuple[str, str]:
    """Build (html, text) bodies for the share email.

    The portal name appears once (brand row); the eyebrow shows the news
    category (or a neutral "Новость") instead of repeating the portal name on
    every line. ``accent_color`` themes the brand strip / eyebrow / CTA.

    The cover image is rendered as a clickable banner linking to the news.
    ``cover_cid`` (a ``Content-ID`` of an inline-embedded image) takes priority
    so the picture shows up even without portal access; ``cover_url`` (absolute)
    is the remote fallback when embedding is unavailable.
    """
    title_esc = _esc(news_title)
    portal_esc = _esc(portal_name)
    link_esc = _esc(news_link)
    portal_url_esc = _esc(portal_url)
    accent_esc = _esc((accent_color or _DEFAULT_ACCENT).strip())
    eyebrow_plain = category.strip() or "Новость"
    eyebrow_esc = _esc(eyebrow_plain.upper())
    excerpt_html = _esc(excerpt).replace("\n", "<br>")

    cover_src = f"cid:{_esc(cover_cid)}" if cover_cid else (_esc(cover_url) if cover_url else "")
    cover_block = ""
    if cover_src:
        cover_block = (
            f'<tr><td style="padding:0;line-height:0;font-size:0">'
            f'<a href="{link_esc}" style="display:block;text-decoration:none">'
            f'<img src="{cover_src}" alt="{title_esc}" width="600" '
            f'style="display:block;width:100%;max-width:600px;height:auto;border:0"></a></td></tr>'
        )

    portal_link_html = ""
    portal_link_text = ""
    if portal_url:
        portal_link_html = (
            f'<p class="email-muted" style="font-size:13px;color:#5b6470;margin:0 0 10px;line-height:1.6;text-align:center">'
            f'<a href="{portal_url_esc}" style="color:#1d4e89;text-decoration:underline">'
            f"Открыть портал</a></p>"
        )
        portal_link_text = f"\nОткрыть портал: {portal_url}"

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>{title_esc}</title>
  <style>{_DARK_STYLE}</style>
</head>
<body class="email-bg" style="margin:0;padding:0;background:#eef1f5;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#2b2f36">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="email-bg" style="background:#eef1f5">
    <tr><td align="center" style="padding:32px 16px">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" class="email-card" style="width:600px;max-width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(20,58,102,0.08)">
        <tr>
          <td class="email-brand" style="padding:18px 28px;border-bottom:1px solid #eceef2">
            <table role="presentation" cellpadding="0" cellspacing="0"><tr>
              <td style="width:4px;background:{accent_esc};border-radius:2px" valign="middle">&nbsp;</td>
              <td style="padding-left:12px" valign="middle">
                <span class="email-brand-name" style="font-size:16px;font-weight:bold;color:#143a66;letter-spacing:.01em">{portal_esc}</span>
              </td>
            </tr></table>
          </td>
        </tr>
        {cover_block}
        <tr>
          <td style="padding:28px 32px">
            <p class="email-eyebrow" style="font-size:12px;color:{accent_esc};margin:0 0 12px;text-transform:uppercase;letter-spacing:.08em;font-weight:bold">{eyebrow_esc}</p>
            <h1 class="email-title" style="font-size:22px;line-height:1.3;color:#143a66;margin:0 0 16px;font-weight:bold">{title_esc}</h1>
            <p class="email-text" style="font-size:15px;color:#3d434c;line-height:1.65;margin:0 0 28px">{excerpt_html}</p>
            <table role="presentation" cellpadding="0" cellspacing="0">
              <tr>
                <td bgcolor="{accent_esc}" style="background:{accent_esc};border-radius:6px">
                  <a href="{link_esc}" style="display:inline-block;padding:13px 30px;font-size:15px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:6px">Читать новость &rarr;</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td class="email-footer" align="center" style="background:#f6f7f9;padding:20px 32px;border-top:1px solid #e6e8ec;text-align:center">
            {portal_link_html}
            <p class="email-muted" style="font-size:13px;color:#5b6470;margin:0 0 10px;line-height:1.6;text-align:center">
              Доступ возможен только из офиса или через корпоративный VPN.
            </p>
            <p class="email-disclaimer" style="font-size:12px;color:#9aa2ad;margin:0;line-height:1.6;text-align:center">
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
        f"{eyebrow_plain}\n\n"
        f"{news_title}\n\n{excerpt}\n\n"
        f"Читать новость: {news_link}{portal_link_text}\n\n"
        f"Доступ возможен только из офиса или через корпоративный VPN.\n"
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

    branding = load_branding_settings()
    news_id: uuid.UUID = news.id

    cover_url = ""
    cover_cid = ""
    payload: dict[str, Any] = {}
    cover_image = getattr(news, "cover_image", None)
    if cover_image:
        if base:
            updated = getattr(news, "updated_at", None)
            version = int(updated.timestamp()) if updated else 0
            cover_url = f"{base}/media/news/{cover_image}?v={version}"
        jpeg = await asyncio.to_thread(build_email_cover_jpeg, _NEWS_MEDIA_DIR / cover_image)
        if jpeg and len(jpeg) <= _MAX_INLINE_COVER_BYTES:
            cover_cid = f"cover-{news_id}"
            payload["inline_images"] = [
                {
                    "cid": cover_cid,
                    "mime": "image/jpeg",
                    "b64": base64.b64encode(jpeg).decode("ascii"),
                }
            ]

    categories = getattr(news, "categories", None) or []
    category = categories[0] if categories else ""

    html, text = build_share_email_content(
        news_title=news.title,
        excerpt=excerpt,
        news_link=news_link,
        portal_url=base,
        portal_name=branding.portal_name,
        cover_url=cover_url,
        cover_cid=cover_cid,
        accent_color=branding.accent_color,
        category=category,
    )
    subject = f"Новость: {news.title}"

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
                    payload=payload or None,
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
