"""HTML / Markdown sanitization helpers.

Centralised here so news/KB/notifications can share one whitelist.
Storage = source-of-truth: sanitize on write (`bleach.clean`), so anything
we read back is already safe. v-html on the frontend is additionally wrapped
in DOMPurify (defense-in-depth).
"""
from __future__ import annotations

import bleach

ALLOWED_TAGS: list[str] = [
    "a", "abbr", "b", "blockquote", "br", "code", "div", "em", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "s",
    "span", "strong", "sub", "sup", "table", "tbody", "td", "th", "thead",
    "tr", "u", "ul",
]

ALLOWED_ATTRS: dict[str, list[str]] = {
    "*": ["class", "id", "style", "title"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "td": ["colspan", "rowspan", "align"],
    "th": ["colspan", "rowspan", "align"],
    "code": ["class"],
    "pre": ["class"],
    "span": ["class", "style"],
    "div": ["class", "style"],
}

ALLOWED_PROTOCOLS: list[str] = ["http", "https", "mailto", "data"]


def sanitize_html(value: str | None) -> str:
    """Clean untrusted HTML body before persisting in DB.

    `data:` is whitelisted only for inline images already produced by our
    own export pipeline; any inline script/style/event handlers are stripped.
    """
    if not value:
        return ""
    return bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def escape_text(value: str | None) -> str:
    """HTML-escape a plain-text string for safe inline interpolation."""
    if not value:
        return ""
    import html as _html

    return _html.escape(value, quote=True)
