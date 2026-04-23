"""XSS sanitization on backend (`bleach.clean` whitelist)."""
from __future__ import annotations

import pytest

from app.core.sanitize import sanitize_html, escape_text


def test_strips_script_tag():
    assert "<script>" not in sanitize_html("<p>ok</p><script>alert(1)</script>")


def test_strips_inline_event_handlers():
    s = sanitize_html('<a href="x" onclick="alert(1)">x</a>')
    assert "onclick" not in s
    assert ">x<" in s or "x</a>" in s


def test_javascript_protocol_rejected():
    s = sanitize_html('<a href="javascript:alert(1)">x</a>')
    assert "javascript:" not in s


def test_data_protocol_for_img_stripped():
    """data: URL removed from ALLOWED_PROTOCOLS (Pre-Phase-4 review P1-6) to close
    `data:text/html,<script>` XSS vector. Inline images for PDF export use
    Playwright with file:// or http:// only, never data: from user content."""
    s = sanitize_html('<img src="data:image/png;base64,AAAA" alt="x">')
    assert "data:image/png" not in s


def test_svg_stripped():
    s = sanitize_html('<svg onload="alert(1)"></svg><p>safe</p>')
    assert "<svg" not in s
    assert "<p>safe</p>" in s


def test_iframe_stripped():
    s = sanitize_html('<iframe src="https://evil"></iframe><p>x</p>')
    assert "<iframe" not in s


def test_style_tag_stripped():
    s = sanitize_html("<style>body{display:none}</style><p>x</p>")
    assert "<style" not in s


def test_meta_stripped():
    s = sanitize_html('<meta http-equiv="refresh" content="0;url=evil">')
    assert "<meta" not in s


def test_object_embed_stripped():
    s = sanitize_html('<object data="evil"></object><embed src="evil">')
    assert "<object" not in s and "<embed" not in s


def test_safe_html_preserved():
    src = "<h2>Заголовок</h2><p><strong>жирный</strong> и <em>курсив</em></p>"
    out = sanitize_html(src)
    assert "<h2>" in out
    assert "<strong>" in out
    assert "<em>" in out


def test_table_tags_preserved():
    src = "<table><thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>"
    out = sanitize_html(src)
    assert "<table>" in out and "<td>" in out and "<th>" in out


def test_empty_input_returns_empty_string():
    assert sanitize_html(None) == ""
    assert sanitize_html("") == ""


def test_escape_text_quotes_and_brackets():
    assert escape_text('<a "b">') == "&lt;a &quot;b&quot;&gt;"


def test_escape_text_none():
    assert escape_text(None) == ""
