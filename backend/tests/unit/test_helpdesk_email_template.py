"""Unit-тесты единого email-шаблона helpdesk (``email_template``).

Чистые функции на заглушках (без БД). Покрывает: шапка с №TKT+темой,
блок ответа агента, reply-разделитель с токеном, alternating-блоки истории
по direction, бейджи ролей, футер, escaping, plain-вариант, empty-history,
round-trip отсечения цитат с новым дизайном маркера.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from app.services.helpdesk.email_quote import (
    REPLY_MARKER_TOKEN,
    strip_quoted_html,
    strip_quoted_reply,
)
from app.services.helpdesk.email_template import (
    build_reply_marker_html,
    build_reply_marker_plain,
    render_history_block,
    render_reply_email,
    render_system_email,
)


def _ticket(*, number: int = 42, subject: str = "Не работает VPN") -> Any:
    return SimpleNamespace(id=uuid.uuid4(), number=number, subject=subject)


def _msg(
    *,
    text: str = "Текст сообщения",
    html: str | None = None,
    direction: str = "inbound",
    author_name: str | None = "Иван Петров",
    author_email: str = "ivan@example.com",
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        body_text=text,
        body_html=html,
        direction=direction,
        author_name=author_name,
        author_email=author_email,
        created_at=created_at or datetime(2026, 7, 1, 10, 0),
    )


# ── Шапка / футер ───────────────────────────────────────────────────────────


class TestHeaderFooter:
    def test_header_contains_ticket_number_and_subject(self) -> None:
        html_out, _ = render_system_email(
            ticket=_ticket(number=77, subject="Тема заявки"),
            body_html="<p>Контент</p>",
            body_text="Контент",
        )
        assert "TKT-77" in html_out
        assert "Тема заявки" in html_out

    def test_footer_contains_portal_link_when_url_given(self) -> None:
        html_out, _ = render_system_email(
            ticket=_ticket(),
            body_html="<p>x</p>",
            body_text="x",
            portal_url="https://portal.local/helpdesk/my/1",
        )
        assert "https://portal.local/helpdesk/my/1" in html_out

    def test_footer_omits_link_when_no_url(self) -> None:
        html_out, _ = render_system_email(
            ticket=_ticket(), body_html="<p>x</p>", body_text="x", portal_url=None
        )
        assert "Открыть заявку" not in html_out
        assert "автоматическое уведомление" in html_out


# ── Блок истории ────────────────────────────────────────────────────────────


class TestRenderHistoryBlock:
    def test_inbound_uses_requester_badge_and_gray_bg(self) -> None:
        out = render_history_block(_msg(direction="inbound", author_name="Анна"))
        assert "Заявитель" in out
        assert "#f5f5f5" in out
        assert "Анна" in out

    def test_outbound_uses_specialist_badge_and_accent_border(self) -> None:
        out = render_history_block(_msg(direction="outbound", author_name="Агент"))
        assert "Специалист" in out
        assert "border-left:3px solid" in out

    def test_author_falls_back_to_email(self) -> None:
        out = render_history_block(_msg(author_name=None, author_email="g@x.test"))
        assert "g@x.test" in out

    def test_body_html_used_when_present(self) -> None:
        out = render_history_block(_msg(html="<p>HTML тело</p>"))
        assert "<p>HTML тело</p>" in out

    def test_plain_body_in_pre_wrap_div_not_pre_tag(self) -> None:
        """Plain-тело оборачивается в <div white-space:pre-wrap>, а не <pre>
        (моноширинный «код»-вид)."""
        out = render_history_block(_msg(text="Строка 1\nСтрока 2", html=None))
        assert "white-space:pre-wrap" in out
        assert "<pre>" not in out

    def test_user_data_escaped(self) -> None:
        out = render_history_block(_msg(author_name="<script>", text="<b>текст</b>", html=None))
        assert "<script>" not in out
        assert "&lt;script&gt;" in out


# ── render_reply_email ──────────────────────────────────────────────────────


class TestRenderReplyEmail:
    def test_wraps_agent_reply_with_header_and_footer(self) -> None:
        html_out, _ = render_reply_email(
            ticket=_ticket(number=5, subject="Тема"),
            agent_body_html="<p>Ответ агентa</p>",
            agent_body_text="Ответ агентa",
            history_html="",
            history_plain="",
        )
        assert "TKT-5" in html_out
        assert "Тема" in html_out
        assert "Ответ агентa" in html_out
        assert "автоматическое уведомление" in html_out

    def test_reply_marker_between_answer_and_history(self) -> None:
        """Маркер (с токеном) стоит между ответом и историей — точка отсечения."""
        html_out, plain_out = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>ОТВЕТ</p>",
            agent_body_text="ОТВЕТ",
            history_html="<div>ИСТОРИЯ</div>",
            history_plain="ИСТОРИЯ",
        )
        assert html_out.index("ОТВЕТ") < html_out.index(REPLY_MARKER_TOKEN)
        assert html_out.index(REPLY_MARKER_TOKEN) < html_out.index("ИСТОРИЯ")
        # Plain — тот же порядок.
        assert plain_out.index("ОТВЕТ") < plain_out.index(REPLY_MARKER_TOKEN)
        assert plain_out.index(REPLY_MARKER_TOKEN) < plain_out.index("ИСТОРИЯ")

    def test_no_history_omits_marker_and_section(self) -> None:
        """Первый ответ — истории нет: разделитель и блок «Предыдущие сообщения»
        не добавляются."""
        html_out, _ = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>Ответ</p>",
            agent_body_text="Ответ",
            history_html="",
            history_plain="",
        )
        assert REPLY_MARKER_TOKEN not in html_out
        assert "Предыдущие сообщения" not in html_out
        assert "Ответ" in html_out

    def test_history_section_has_heading(self) -> None:
        html_out, _ = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>x</p>",
            agent_body_text="x",
            history_html=render_history_block(_msg()),
            history_plain="...",
        )
        assert "Предыдущие сообщения" in html_out

    def test_plain_has_ticket_header_line(self) -> None:
        _, plain_out = render_reply_email(
            ticket=_ticket(number=9, subject="Моя тема"),
            agent_body_html="<p>x</p>",
            agent_body_text="Тело ответа",
            history_html="",
            history_plain="",
        )
        assert "TKT-9" in plain_out
        assert "Моя тема" in plain_out
        assert "Тело ответа" in plain_out


# ── render_system_email ─────────────────────────────────────────────────────


class TestRenderSystemEmail:
    def test_wraps_content_without_marker_or_history(self) -> None:
        html_out, _ = render_system_email(
            ticket=_ticket(number=11, subject="Назначение"),
            body_html="<p>Заявка принята</p>",
            body_text="Заявка принята",
        )
        assert "TKT-11" in html_out
        assert "Назначение" in html_out
        assert "Заявка принята" in html_out
        # Системное письмо — без reply-маркера и истории.
        assert REPLY_MARKER_TOKEN not in html_out
        assert "Предыдущие сообщения" not in html_out


# ── Маркеры ─────────────────────────────────────────────────────────────────


class TestReplyMarkers:
    def test_html_marker_token_hidden_but_present(self) -> None:
        """Токен спрятан в невидимом div (font-size:0, color=фон плашки), но
        физически присутствует — regex _OWN_MARKER_HTML_RE его находит."""
        m = build_reply_marker_html(1)
        assert REPLY_MARKER_TOKEN in m
        assert "font-size:0" in m
        assert "color:#fafafa" in m

    def test_plain_marker_has_token_on_own_line(self) -> None:
        m = build_reply_marker_plain(1)
        assert REPLY_MARKER_TOKEN in m
        assert f"--- {REPLY_MARKER_TOKEN} ---" in m

    def test_html_marker_cut_by_strip(self) -> None:
        """strip_quoted_html отрезает от нового маркера — ответ остаётся, история уходит."""
        m = build_reply_marker_html(1)
        html_body = "<p>ОТВЕТ</p>" + m + "<div>ИСТОРИЯ</div>"
        out = strip_quoted_html(html_body)
        assert "ОТВЕТ" in out
        assert "ИСТОРИЯ" not in out

    def test_plain_marker_cut_by_strip(self) -> None:
        m = build_reply_marker_plain(1)
        text = "Спасибо!" + m + "история\nещё"
        assert strip_quoted_reply(text) == "Спасибо!"


# ── Round-trip: ответ заявителя через Outlook → чистый текст ────────────────


class TestRoundTripOutlook:
    """Полный сценарий: агент ответил (шаблон с маркером) → заявитель ответил
    через Outlook (цитата под From:/Sent:) → ingress режет → чистый ответ."""

    def test_full_roundtrip(self) -> None:
        ticket = _ticket(number=202, subject="тест")
        html_email, _plain_email = render_reply_email(
            ticket=ticket,
            agent_body_html="<p>ага да очень труньк</p>",
            agent_body_text="ага да очень труньк",
            history_html=render_history_block(_msg(text="Труньки")),
            history_plain="От Заявитель, 01.07.2026:\n> Труньки",
        )
        # Заявитель отвечает через Outlook: сверху его ответ, ниже — quote-header
        # + процитированное наше письмо целиком.
        inbound_html = (
            '<div class="WordSection1">'
            "<p>Точно ли труньк?</p>"
            "<div><p><b><span>From:</span></b><span> portal@x.test</span></p></div>"
            + html_email
            + "</div>"
        )
        out = strip_quoted_html(inbound_html)
        assert "Точно ли труньк?" in out
        # Ответ агента (над маркером, под From:) — отрезан.
        assert "ага да очень труньк" not in out
        # История — отрезана маркером.
        assert "Труньки" not in out
        assert REPLY_MARKER_TOKEN not in out
