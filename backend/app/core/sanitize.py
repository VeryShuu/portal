"""HTML / Markdown sanitization helpers.

Centralised here so news/KB/notifications can share one whitelist.
Storage = source-of-truth: sanitize on write (`nh3.clean`), so anything
we read back is already safe. v-html on the frontend is additionally wrapped
in DOMPurify (defense-in-depth).
"""

from __future__ import annotations

import nh3

ALLOWED_TAGS: set[str] = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
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
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "span",
    "strong",
    "sub",
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
    "div": {"class"},
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
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        url_schemes=_URL_SCHEMES,
        strip_comments=True,
    )


def escape_text(value: str | None) -> str:
    """HTML-escape a plain-text string for safe inline interpolation."""
    if not value:
        return ""
    import html as _html

    return _html.escape(value, quote=True)
