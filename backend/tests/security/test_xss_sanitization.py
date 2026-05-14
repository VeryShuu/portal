"""XSS sanitization on backend (`nh3.clean` whitelist)."""

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


def test_iframe_allowed_for_embed_video():
    """iframe is whitelisted at backend level for video embeds (see Step 8.6).
    Frontend ``sanitizeHtmlAllowIframe`` enforces per-origin allowlist on render."""
    s = sanitize_html('<iframe src="https://video.company.local/embed/x"></iframe><p>x</p>')
    assert "<iframe" in s
    assert "<p>x</p>" in s


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


# --- Bypass-vector regression suite ---------------------------------------
# These tests pin down behaviour for non-obvious XSS payloads. nh3 / ammonia
# already handles them correctly; the goal is to fail loudly if a future
# allowlist edit ever loosens this contract.


def test_svg_with_nested_script_stripped():
    s = sanitize_html("<svg><script>alert(1)</script></svg><p>safe</p>")
    assert "<svg" not in s
    assert "<script" not in s
    assert "alert(1)" not in s
    assert "<p>safe</p>" in s


def test_svg_self_closing_with_event_stripped():
    s = sanitize_html("<div><svg/onload=alert(1)></div>")
    assert "<svg" not in s
    assert "onload" not in s
    assert "alert" not in s


def test_mathml_with_nested_script_stripped():
    s = sanitize_html("<math><mtext><script>alert(1)</script></mtext></math><p>x</p>")
    assert "<math" not in s
    assert "<mtext" not in s
    assert "<script" not in s
    assert "alert(1)" not in s
    assert "<p>x</p>" in s


def test_img_onerror_polyglot_stripped():
    s = sanitize_html("<img src=x onerror=alert(1)>")
    assert "onerror" not in s
    assert "alert" not in s


def test_javascript_void_protocol_rejected():
    s = sanitize_html('<a href="javascript:void(0)">x</a>')
    assert "javascript:" not in s
    assert "void" not in s


def test_javascript_protocol_uppercase_rejected():
    s = sanitize_html('<a href="JAVASCRIPT:alert(1)">x</a>')
    assert "javascript:" not in s.lower()
    assert "alert" not in s


def test_javascript_protocol_with_leading_space_rejected():
    s = sanitize_html('<a href="  javascript:alert(1)">x</a>')
    assert "javascript:" not in s
    assert "alert" not in s


def test_vbscript_protocol_rejected():
    s = sanitize_html('<a href="vbscript:alert(1)">x</a>')
    assert "vbscript:" not in s
    assert "alert" not in s


def test_css_url_javascript_in_style_stripped():
    s = sanitize_html('<p style="background:url(javascript:alert(1))">x</p>')
    assert "background" not in s
    assert "javascript" not in s
    assert "url(" not in s
    assert "<p>x</p>" in s


def test_css_expression_in_style_stripped():
    s = sanitize_html('<div style="xss:expression(alert(1))">x</div>')
    assert "expression" not in s
    assert "alert" not in s


def test_text_align_style_preserved_as_contract():
    s = sanitize_html('<p style="text-align:center">good</p>')
    assert 'style="text-align:center"' in s
    assert "<p" in s


def test_form_with_javascript_action_stripped():
    s = sanitize_html('<form action="javascript:alert(1)"><input></form>')
    assert "<form" not in s
    assert "<input" not in s
    assert "javascript:" not in s


def test_base_tag_stripped():
    s = sanitize_html('<base href="javascript:alert(1)">')
    assert "<base" not in s
    assert "javascript:" not in s


def test_html_conditional_comment_stripped():
    s = sanitize_html("<!--[if IE]><script>alert(1)</script><![endif]--><p>x</p>")
    assert "<script" not in s
    assert "<!--" not in s
    assert "alert(1)" not in s
    assert "<p>x</p>" in s


def test_noscript_payload_neutralised():
    """nh3 strips <noscript> and HTML-escapes its contents so any nested
    markup is rendered as inert text rather than re-parsed by the browser."""
    s = sanitize_html("<noscript><p>x</p></noscript>")
    assert "<noscript" not in s
    assert "<p>x</p>" not in s


def test_mutation_xss_broken_tag_does_not_resurrect_script():
    """Payloads that try to smuggle a script via reparse-on-serialize must
    not survive sanitisation in any form executable by a browser."""
    s = sanitize_html("<noscript><p title=\"</noscript><script>alert(1)</script>\">x</p></noscript>")
    assert "<script" not in s
    assert "alert(1)" not in s


def test_unknown_xss_tag_with_inline_handler_stripped():
    s = sanitize_html("<xss style=xss:expression(alert(1))>x</xss>")
    assert "<xss" not in s
    assert "expression" not in s
    assert "alert" not in s


def test_anchor_target_blank_gets_rel_noopener():
    """Defense-in-depth: nh3 forces rel=noopener noreferrer on links so a
    malicious target page cannot reach window.opener."""
    s = sanitize_html('<a href="https://example.com" target="_blank">x</a>')
    assert "noopener" in s
    assert "noreferrer" in s
