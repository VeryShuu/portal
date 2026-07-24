"""HTML / Markdown sanitization helpers.

Centralised here so news/KB/notifications can share one whitelist.
Storage = source-of-truth: sanitize on write (`nh3.clean`), so anything
we read back is already safe. v-html on the frontend is additionally wrapped
in DOMPurify (defense-in-depth).
"""

from __future__ import annotations

import re as _re_mod
from typing import cast

import nh3

# Tags allowed to carry an inline ``style`` attribute (only ``text-align``
# values pass through ``_attribute_filter`` below).
_TEXT_ALIGN_TAGS: set[str] = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "div"}
_TEXT_ALIGN_RE = _re_mod.compile(
    r"^\s*text-align\s*:\s*(left|center|right|justify)\s*;?\s*$",
    _re_mod.IGNORECASE,
)
_IFRAME_SANDBOX_RE = _re_mod.compile(
    r'(<iframe\b[^>]*?)(?:\s+sandbox="[^"]*")?(>)',
    _re_mod.IGNORECASE,
)
_IFRAME_TAG_RE = _re_mod.compile(
    r"<iframe\b([^>]*)>.*?</iframe>",
    _re_mod.IGNORECASE | _re_mod.DOTALL,
)
_IFRAME_SRC_RE = _re_mod.compile(
    r"""\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""",
    _re_mod.IGNORECASE,
)

# Mirrors frontend whitelist in
# frontend/src/components/editor/extensions/IframeEmbed.ts
ALLOWED_IFRAME_DOMAINS: tuple[str, ...] = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "rutube.ru",
    "vimeo.com",
    "vk.com",
    "vk.video",
    "company.local",
    "video.company.local",
)


def _iframe_src_is_allowed(src: str | None) -> bool:
    if not src:
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(src.strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if any(host == d or host.endswith("." + d) for d in ALLOWED_IFRAME_DOMAINS):
        return True

    try:
        from app.core.system_config import load_system_settings

        settings = load_system_settings()
        if settings and settings.video_gallery_url:
            gallery_parsed = urlparse(settings.video_gallery_url.strip())
            gallery_host = (gallery_parsed.hostname or "").lower()
            if gallery_host and (host == gallery_host or host.endswith("." + gallery_host)):
                return True
    except Exception:
        pass

    return False


def _strip_disallowed_iframes(html: str) -> str:
    def _replace(match: _re_mod.Match[str]) -> str:
        attrs = match.group(1) or ""
        src_match = _IFRAME_SRC_RE.search(attrs)
        src = None
        if src_match:
            src = src_match.group(1) or src_match.group(2) or src_match.group(3)
        if _iframe_src_is_allowed(src):
            return match.group(0)
        return ""

    return _IFRAME_TAG_RE.sub(_replace, html)


_MD_AUTOLINK_URL_RE = _re_mod.compile(
    r"<((?:https?|mailto|tel):[^\s<>]+)>",
    _re_mod.IGNORECASE,
)
_MD_AUTOLINK_EMAIL_RE = _re_mod.compile(
    r"<([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})>",
    _re_mod.IGNORECASE,
)


def _attribute_filter(tag: str, attr: str, value: str) -> str | None:
    """nh3 attribute filter: keep only ``text-align`` in ``style``; normalise iframe sandbox."""
    if tag == "iframe":
        if attr == "sandbox":
            return "allow-scripts allow-same-origin"
        return value
    if tag == "input":
        if attr == "type":
            return "checkbox" if (value or "").lower() == "checkbox" else None
        return value
    if attr != "style":
        return value
    if tag not in _TEXT_ALIGN_TAGS:
        return None
    if _TEXT_ALIGN_RE.match((value or "").strip()):
        return value.strip().rstrip(";").strip()
    return None


ALLOWED_TAGS: set[str] = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "details",
    "div",
    "em",
    "figcaption",
    "figure",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "iframe",
    "img",
    "input",
    "label",
    "li",
    "mark",
    "ol",
    "p",
    "pre",
    "s",
    "span",
    "strong",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

ALLOWED_ATTRS: dict[str, set[str]] = {
    "*": {"class", "id", "title"},
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height"},
    "iframe": {"src", "width", "height", "allowfullscreen", "sandbox", "loading", "title"},
    "td": {"colspan", "rowspan", "align"},
    "th": {"colspan", "rowspan", "align"},
    "code": {"class"},
    "pre": {"class"},
    "span": {"class"},
    "div": {"class", "style"},
    "details": {"open"},
    "p": {"style"},
    "h1": {"style"},
    "h2": {"style"},
    "h3": {"style"},
    "h4": {"style"},
    "h5": {"style"},
    "h6": {"style"},
    "input": {"type", "checked", "disabled"},
    "label": {"class"},
    "li": {"class", "data-checked", "data-type"},
    "ul": {"class", "data-type"},
}

_URL_SCHEMES: set[str] = {"http", "https", "mailto"}


def sanitize_html(value: str | None) -> str:
    """Clean untrusted HTML body before persisting in DB.

    `data:` URIs are intentionally NOT whitelisted: they would otherwise
    allow ``data:text/html,<script>...`` on `<a href>` (XSS vector). Inline
    base64 images for PDF export are produced server-side and bypass this
    sanitizer entirely.
    """
    if not value:
        return ""
    cleaned = nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        attribute_filter=_attribute_filter,
        url_schemes=_URL_SCHEMES,
        strip_comments=True,
    )
    cleaned = _IFRAME_SANDBOX_RE.sub(r'\1 sandbox="allow-scripts allow-same-origin"\2', cleaned)
    cleaned = _strip_disallowed_iframes(cleaned)
    return cleaned


def sanitize_markdown(value: str | None) -> str:
    """Clean untrusted Markdown body before persisting in DB.

    Markdown autolinks (``<https://example.com>``, ``<user@example.com>``) look
    like unknown HTML tags to ``nh3`` and would be stripped together with their
    contents, so we rewrite them into the inline ``[url](url)`` form first.
    Then the standard HTML sanitizer runs to defang any actual HTML.
    """
    if not value:
        return ""
    value = _MD_AUTOLINK_URL_RE.sub(r"[\1](\1)", value)
    value = _MD_AUTOLINK_EMAIL_RE.sub(r"[\1](mailto:\1)", value)
    return sanitize_html(value)


def clean_title(value: str | None) -> str:
    if not value:
        return ""
    return cast(str, nh3.clean(value, tags=set(), strip_comments=True))


def escape_text(value: str | None) -> str:
    """HTML-escape a plain-text string for safe inline interpolation."""
    if not value:
        return ""
    import html as _html

    return _html.escape(value, quote=True)
