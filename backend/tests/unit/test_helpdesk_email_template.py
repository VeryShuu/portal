"""Unit-тесты единого email-шаблона helpdesk (``email_template``).

Чистые функции на заглушках (без БД). Покрывает минималистичный дизайн
(GitHub/Linear-уровня):

* компактная шапка: № тикета + тема + статус (точка+лейбл) + исполнитель + последнее
  обновление;
* таймлайн переписки: тонкий разделитель сверху + имя (accent/grey) + дата + тело,
  у специалиста — левая полоса accent; без карточек/бейджей/теней;
* блок ответа агента — таймлайн outbound-стиля без верхнего разделителя;
* reply-разделитель с токеном (двойная линия + ↩);
* футер, escaping, plain-вариант, empty-history, round-trip отсечения цитат.
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


def _ticket(
    *,
    number: int = 42,
    subject: str = "Не работает VPN",
    status: str = "open",
    last_activity_at: datetime | None = None,
) -> Any:
    # ``assignee_full_name`` намеренно НЕ атрибут тикета-заглушки: в реальном
    # коде это отдельный kwarg рендер-функций (пробрасывается из call-сайтов,
    # см. ``outbound.py``/``notifications.py``), а ORM-тикет несёт relationship
    # ``assignee``. Тесты передают его явно в вызовы render_*.
    return SimpleNamespace(
        id=uuid.uuid4(),
        number=number,
        subject=subject,
        status=status,
        last_activity_at=last_activity_at or datetime(2026, 7, 12, 1, 48),
    )


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


# ── Шапка ──────────────────────────────────────────────────────────────────


class TestHeader:
    def test_header_contains_ticket_number_and_subject(self) -> None:
        html_out, _ = render_system_email(
            ticket=_ticket(number=77, subject="Тема заявки"),
            body_html="<p>Контент</p>",
            body_text="Контент",
        )
        assert "#77" in html_out
        assert "Тема заявки" in html_out

    def test_header_number_and_subject_same_line_same_font(self) -> None:
        """Номер и тема — в одной строке, одним шрифтом, через дефис:
        «#номер — тема». Единый размер 14px, иерархия через вес/цвет (не размеры)."""
        html_out, _ = render_system_email(
            ticket=_ticket(number=642, subject="Не работает принтер"),
            body_html="<p>x</p>",
            body_text="x",
        )
        # Единая строка заголовка.
        assert "#642 — Не работает принтер" in html_out
        # Жёсткий шрифт Times New Roman, размер 14px (не 22px).
        assert "'Times New Roman'" in html_out
        assert "font-size:14px" in html_out
        # Крупных размеров больше нет — вся иерархия в 14px.
        assert "font-size:22px" not in html_out

    def test_header_has_no_assignee_line(self) -> None:
        """Строка «Исполнитель» убрана из шапки (по требованию). Роль видна в
        таймлайне по подписи «Исполнитель»/«Специалист поддержки»."""
        html_out, _ = render_system_email(
            ticket=_ticket(), body_html="<p>x</p>", body_text="x"
        )
        assert "Исполнитель:" not in html_out
        assert "Не назначен" not in html_out

    def test_header_no_brand_band(self) -> None:
        """Шапка — белая, без насыщенной цветной полосы (старый ``#143a66`` ушёл)."""
        html_out, _ = render_system_email(
            ticket=_ticket(), body_html="<p>x</p>", body_text="x"
        )
        assert "#143a66" not in html_out
        assert "background:#143a66" not in html_out

    def test_header_has_no_status(self) -> None:
        """Статус убран из шапки письма (по требованию). Ни лейблов, ни
        цветного индикатора в шапке быть не должно."""
        html_out, _ = render_system_email(
            ticket=_ticket(status="open"), body_html="<p>x</p>", body_text="x"
        )
        assert "В работе" not in html_out
        assert "Ожидание" not in html_out
        assert "Решено" not in html_out
        assert "🟢" not in html_out
        assert "🟡" not in html_out
        assert "🔵" not in html_out

    def test_header_has_no_last_update(self) -> None:
        """Строка «Последнее обновление» убрана из шапки (по требованию)."""
        html_out, _ = render_system_email(
            ticket=_ticket(last_activity_at=datetime(2026, 7, 12, 1, 48)),
            body_html="<p>x</p>",
            body_text="x",
        )
        assert "Последнее обновление" not in html_out

    def test_header_subject_escaped(self) -> None:
        html_out, _ = render_system_email(
            ticket=_ticket(subject="<script>alert(1)</script>"),
            body_html="<p>x</p>",
            body_text="x",
        )
        assert "<script>" not in html_out
        assert "&lt;script&gt;" in html_out


# ── Футер ──────────────────────────────────────────────────────────────────


class TestFooter:
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
        # Новый призыв ответить на письмо (вместо старого «автоматическое уведомление»).
        assert "ответив на это письмо" in html_out

    def test_footer_centered_bold_cta(self) -> None:
        """Призыв ответить — по центру письма, жирный."""
        html_out, _ = render_system_email(
            ticket=_ticket(), body_html="<p>x</p>", body_text="x"
        )
        assert "text-align:center" in html_out
        assert "font-weight:600" in html_out
        assert "Вы можете оставить комментарии по заявке ответив на это письмо" in html_out


# ── Блок таймлайна ──────────────────────────────────────────────────────────


class TestRenderHistoryBlock:
    def test_inbound_requester_name_in_grey(self) -> None:
        out = render_history_block(_msg(direction="inbound", author_name="Анна"))
        assert "Анна" in out
        # Имя заявителя — secondary grey.
        assert "#57606a" in out
        # Левых вертикальных полос нет (по запросу) — различение только цветом имени.
        assert "border-left" not in out
        assert "#0969da" not in out

    def test_outbound_specialist_name_in_accent(self) -> None:
        out = render_history_block(_msg(direction="outbound", author_name="Агент"))
        assert "Агент" in out
        assert "#0969da" in out
        # Левых вертикальных полос нет (по запросу).
        assert "border-left" not in out

    def test_outbound_specialist_role_prefix_then_name(self) -> None:
        """Подпись специалиста: префикс «Специалист поддержки — » (приглушённым
        цветом) перед именем (accent). Роль и имя в разных <span>, поэтому
        проверяем раздельно — порядок: роль с тире, затем имя."""
        out = render_history_block(_msg(direction="outbound", author_name="Агент"))
        assert "Специалист поддержки — " in out
        assert "Агент" in out
        assert out.index("Специалист поддержки") < out.index("Агент")

    def test_outbound_assignee_role_prefix_then_name(self) -> None:
        """Если автор = назначенный исполнитель → префикс «Исполнитель — »."""
        author_id = uuid.uuid4()
        msg = _msg(direction="outbound", author_name="Агент")
        msg.author_user_id = author_id
        out = render_history_block(msg, assignee_user_id=author_id)
        assert "Исполнитель — " in out
        assert "Специалист поддержки" not in out

    def test_inbound_has_no_role_prefix(self) -> None:
        """Заявителю префикс роли не добавляется — только имя."""
        out = render_history_block(_msg(direction="inbound", author_name="Заявитель"))
        assert "Специалист поддержки" not in out
        assert "Исполнитель" not in out
        assert "Заявитель" in out

    def test_timeline_block_has_no_date(self) -> None:
        """Дата/время НЕ выводятся в блоках таймлайна (по запросу — дата в письме)."""
        out = render_history_block(
            _msg(direction="inbound", created_at=datetime(2026, 7, 14, 13, 19))
        )
        assert "14.07.2026" not in out
        assert "13:19" not in out

    def test_no_card_chrome(self) -> None:
        """Минимализм: нет карточек/бейджей/теней/скруглений (старый дизайн ушёл)."""
        out = render_history_block(_msg(direction="inbound"))
        assert "box-shadow" not in out
        assert "border-radius" not in out

    def test_separator_before_each_history_block(self) -> None:
        """Каждый блок истории начинается с горизонтального разделителя ``<hr>``
        на всю ширину письма (отдельный элемент, не ``border-top`` на блоке —
        чтобы не пересекаться с левой цветной полосой сообщения)."""
        out = render_history_block(_msg(direction="inbound"))
        assert '<hr style="border:none;border-top:1px solid #d8dee4' in out

    def test_no_separator_on_agent_reply_block(self) -> None:
        """Блок ответа агента (в ``render_reply_email``) идёт сразу после шапки —
        без разделителя перед ним (он был бы лишним шумом под шапкой)."""
        html_out, _ = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>ответ</p>",
            agent_body_text="ответ",
            history_html="",
            history_plain="",
        )
        # В блоке ответа агента ``<hr>`` нет (он есть только в истории).
        # Проверяем: после шапки идёт блок ответа без ведущего <hr>.
        assert "<hr" not in html_out

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
        assert "#5" in html_out
        assert "Тема" in html_out
        assert "Ответ агентa" in html_out
        # Новый футер-призыв ответить на письмо (вместо старого «автоматическое уведомление»).
        assert "ответив на это письмо" in html_out

    def test_no_reply_marker_in_email(self) -> None:
        """Reply-маркер («Ответьте выше этой линии») НЕ ставится в письмо —
        отсечение цитат работает по заголовкам почтового клиента (как в OTRS),
        не по нашему служебному блоку. См. ``strip_quoted_reply``/``strip_quoted_html``."""
        html_out, plain_out = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>ОТВЕТ</p>",
            agent_body_text="ОТВЕТ",
            history_html="<div>ИСТОРИЯ</div>",
            history_plain="ИСТОРИЯ",
        )
        assert REPLY_MARKER_TOKEN not in html_out
        assert REPLY_MARKER_TOKEN not in plain_out
        # «↩» — тоже признак старого блока-маркера.
        assert "↩" not in html_out
        # Ответ и история всё равно присутствуют (история под заголовком).
        assert "ОТВЕТ" in html_out
        assert "ИСТОРИЯ" in html_out

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

    def test_history_has_no_heading(self) -> None:
        """Заголовок «Предыдущие сообщения» убран (по запросу). История идёт
        сразу за ответом агента, разделяясь ``<hr>`` блоков истории."""
        html_out, _ = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>x</p>",
            agent_body_text="x",
            history_html=render_history_block(_msg()),
            history_plain="...",
        )
        assert "Предыдущие сообщения" not in html_out
        # Сама история присутствует.
        assert "<hr" in html_out

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

    def test_agent_reply_block_uses_outbound_timeline_style(self) -> None:
        """Блок ответа агента — accent-имя (без левой полосы и без разделителя:
        блок идёт сразу после шапки)."""
        html_out, _ = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>тело ответа</p>",
            agent_body_text="тело ответа",
            history_html="",
            history_plain="",
            message_author="Administrator",
        )
        # Outbound-стиль: имя в accent-цвете. Левых полос нет (по запросу).
        assert "#0969da" in html_out
        assert "border-left" not in html_out
        assert "Administrator" in html_out

    def test_agent_reply_assignee_executor_prefix(self) -> None:
        """Автор ответа = назначенный исполнитель → префикс «Исполнитель — »."""
        author_id = uuid.uuid4()
        html_out, _ = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>x</p>",
            agent_body_text="x",
            history_html="",
            history_plain="",
            message_author="Administrator",
            assignee_user_id=author_id,
            message_author_user_id=author_id,
        )
        assert "Исполнитель — " in html_out
        assert "Administrator" in html_out

    def test_agent_reply_non_assignee_specialist_prefix(self) -> None:
        """Ответ агента, не назначенного исполнителем → префикс «Специалист поддержки — »."""
        html_out, _ = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>x</p>",
            agent_body_text="x",
            history_html="",
            history_plain="",
            message_author="Другой агент",
            assignee_user_id=uuid.uuid4(),
            message_author_user_id=uuid.uuid4(),
        )
        assert "Специалист поддержки — " in html_out
        assert "Другой агент" in html_out

    def test_agent_reply_header_has_no_assignee(self) -> None:
        """Исполнитель убран из шапки письма (по требованию) — assignee_full_name
        больше не передаётся в render_reply_email."""
        html_out, _ = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>x</p>",
            agent_body_text="x",
            history_html="",
            history_plain="",
        )
        assert "Исполнитель:" not in html_out


# ── render_system_email ─────────────────────────────────────────────────────


class TestRenderSystemEmail:
    def test_wraps_content_without_marker_or_history(self) -> None:
        html_out, _ = render_system_email(
            ticket=_ticket(number=11, subject="Назначение"),
            body_html="<p>Заявка принята</p>",
            body_text="Заявка принята",
        )
        assert "#11" in html_out
        assert "Назначение" in html_out
        assert "Заявка принята" in html_out
        # Системное письмо — без reply-маркера и истории.
        assert REPLY_MARKER_TOKEN not in html_out
        assert "Предыдущие сообщения" not in html_out

    def test_system_email_has_no_assignee_in_header(self) -> None:
        """Системное письмо тоже без строки исполнителя в шапке."""
        html_out, _ = render_system_email(
            ticket=_ticket(),
            body_html="<p>x</p>",
            body_text="x",
        )
        assert "Исполнитель:" not in html_out


# ── Маркеры ─────────────────────────────────────────────────────────────────


class TestReplyMarkers:
    def test_html_marker_token_is_visible_text(self) -> None:
        """``REPLY_MARKER_TOKEN`` — видимый текст плашки (↩ + фраза), не скрытый
        div. Скрытые узлы (font-size:0) ненадёжно переживают ответ в Outlook,
        поэтому якорь отсечения — сам видимый текст инструкции."""
        m = build_reply_marker_html(1)
        assert REPLY_MARKER_TOKEN in m
        assert "↩" in m
        # Скрытых узлов нет.
        assert "font-size:0" not in m

    def test_html_marker_has_new_visual(self) -> None:
        """Полировка: двойная линия с контрастом (border-top/bottom 3px #b8c2cc),
        увеличенные отступы (18px 20px), ↩."""
        m = build_reply_marker_html(1)
        assert "↩" in m
        assert "Ответьте выше этой линии" in m
        assert "border-top:3px solid #b8c2cc" in m
        assert "border-bottom:3px solid #b8c2cc" in m
        assert "padding:18px 20px" in m

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


# ── Отсечение подписи отправителя (эвристика) ────────────────────────────────


class TestSignatureStripping:
    """Эвристика отсечения автоматической email-подписи отправителя. Применяется
    в письме (через ``_message_body_html``): подпись замещается блоком «Подпись
    скрыта», в БД и веб-версии тикета остаётся полностью."""

    def test_plain_rfc3676_separator(self) -> None:
        from app.services.helpdesk.email_template import _split_signature_plain

        text = (
            "Принтер не работает уже третий день. Помогите, пожалуйста.\n\n"
            "-- \nВячеслав Борзихин\nИнженер\n+7 999 123-45-67"
        )
        body, had = _split_signature_plain(text)
        assert had is True
        assert "Вячеслав Борзихин" not in body
        assert "Помогите, пожалуйста" in body

    def test_plain_russian_regards(self) -> None:
        from app.services.helpdesk.email_template import _split_signature_plain

        text = (
            "Добрый день! Не получается подключиться к VPN с домашнего ноутбука.\n\n"
            "С уважением,\nИван Петров\nОтдел кадров"
        )
        body, had = _split_signature_plain(text)
        assert had is True
        assert "Иван Петров" not in body
        assert "подключиться к VPN" in body

    def test_plain_english_regards(self) -> None:
        from app.services.helpdesk.email_template import _split_signature_plain

        text = "Thanks, that fixed it!\n\nBest regards,\nJohn Smith\nIT Department"
        body, had = _split_signature_plain(text)
        assert had is True
        assert "John Smith" not in body

    def test_plain_no_signature_unchanged(self) -> None:
        from app.services.helpdesk.email_template import _split_signature_plain

        text = "Короткий ответ без подписи но длиннее сорока символов."
        body, had = _split_signature_plain(text)
        assert had is False
        assert body == text

    def test_plain_short_body_skipped(self) -> None:
        from app.services.helpdesk.email_template import _split_signature_plain

        # Короче _SIG_MIN_LEN — не ищем подпись.
        body, had = _split_signature_plain("Спасибо!")
        assert had is False
        assert body == "Спасибо!"

    def test_plain_regards_at_start_not_stripped(self) -> None:
        """«С уважением» в начале ответа (не подпись, а часть текста) — не
        отсекается."""
        from app.services.helpdesk.email_template import _split_signature_plain

        text = (
            "С уважением отношусь к вашей работе, но принтер всё ещё не работает. "
            "Уже неделю жду."
        )
        body, had = _split_signature_plain(text)
        assert had is False
        assert body == text

    def test_html_hr_separator(self) -> None:
        from app.services.helpdesk.email_template import _split_signature_html

        h = "<p>Thanks, that fixed it!</p><hr><p>John Smith<br>IT Dept</p>"
        body, had = _split_signature_html(h)
        assert had is True
        assert "John Smith" not in body
        assert "fixed it" in body

    def test_html_regards_with_inline_tags(self) -> None:
        """Формула вежливости в HTML с inline-тегами (<b>/<br>) ловится."""
        from app.services.helpdesk.email_template import _split_signature_html

        h = (
            "<p>Принтер сломался, нужна помощь.</p>"
            "<p>С уважением,<br><b>Вячеслав Борзихин</b><br>Инженер</p>"
        )
        body, had = _split_signature_html(h)
        assert had is True
        assert "Вячеслав Борзихин" not in body
        assert "нужна помощь" in body

    def test_html_no_signature_unchanged(self) -> None:
        from app.services.helpdesk.email_template import _split_signature_html

        h = "<p>Короткий ответ без подписи.</p>"
        body, had = _split_signature_html(h)
        assert had is False
        assert body == h

    def test_message_body_renders_hidden_block_when_signature_present(self) -> None:
        """При наличии подписи в теле сообщения рендерится блок «Подпись скрыта»."""
        msg = _msg(
            text=(
                "Спасибо за помощь, всё работает.\n\n"
                "С уважением,\nИван Петров\nОтдел кадров"
            ),
            html=None,
        )
        from app.services.helpdesk.email_template import _message_body_html

        out = _message_body_html(msg)
        assert "Подпись отправителя скрыта" in out
        # Сам текст подписи убран из тела.
        assert "Иван Петров" not in out

    def test_message_body_no_hidden_block_without_signature(self) -> None:
        msg = _msg(text="Спасибо за помощь, всё работает отлично!", html=None)
        from app.services.helpdesk.email_template import _message_body_html

        out = _message_body_html(msg)
        assert "Подпись отправителя скрыта" not in out


# ── Блок вложений ────────────────────────────────────────────────────────────


class TestAttachmentsBlock:
    def test_attachments_render_as_compact_list_with_size(self) -> None:
        from app.services.helpdesk.email_template import _attachments_list_html

        atts = [
            SimpleNamespace(
                id=uuid.uuid4(), original_name="scan.pdf", size_bytes=3489123
            ),
            SimpleNamespace(
                id=uuid.uuid4(), original_name="photo.jpg", size_bytes=51200
            ),
        ]
        out = _attachments_list_html(atts)
        # Заголовок «📎 Вложения».
        assert "📎 Вложения" in out
        # Имена файлов.
        assert "scan.pdf" in out
        assert "photo.jpg" in out
        # Размер (человекочитаемый).
        assert "KB" in out
        # Ссылки абсолютные.
        assert "/api/v1/helpdesk/attachments/" in out

    def test_empty_attachments_returns_empty(self) -> None:
        from app.services.helpdesk.email_template import _attachments_list_html

        assert _attachments_list_html([]) == ""
        assert _attachments_list_html(None) == ""

    def test_format_size_human_readable(self) -> None:
        from app.services.helpdesk.email_template import _format_size

        assert _format_size(0) == "0 B"
        assert _format_size(512) == "512 B"
        assert _format_size(1536) == "1.5 KB"
        assert _format_size(1048576) == "1.0 MB"
        assert _format_size(None) == ""
        assert _format_size("abc") == ""


# ── Визуальная иерархия шапки ─────────────────────────────────────────────────


class TestVisualHierarchy:
    """Шапка: единый заголовок «#номер — тема» одним шрифтом/размером. Иерархия
    во всём письме — через font-weight/color, не через размеры (жёсткий 14px)."""

    def test_single_font_size_throughout(self) -> None:
        """Во всём письме один размер — 14px (никаких 22px/13px/12px)."""
        html_out, _ = render_system_email(
            ticket=_ticket(subject="Моя тема заявки"),
            body_html="<p>x</p>",
            body_text="x",
        )
        assert "font-size:14px" in html_out
        assert "font-size:22px" not in html_out
        assert "font-size:13px" not in html_out
        assert "font-size:12px" not in html_out

    def test_header_no_status_no_update_no_assignee(self) -> None:
        """В шапке нет ни статуса, ни строки обновления, ни исполнителя —
        только № + тема (по требованию)."""
        html_out, _ = render_system_email(
            ticket=_ticket(status="open"), body_html="<p>x</p>", body_text="x"
        )
        assert "Последнее обновление" not in html_out
        assert "В работе" not in html_out
        assert "Исполнитель:" not in html_out

    def test_no_heavy_chrome_anywhere(self) -> None:
        """Ниже шапки — никаких тяжёлых рамок/теней/скруглений (п.12 концепция)."""
        html_out, _ = render_reply_email(
            ticket=_ticket(),
            agent_body_html="<p>ответ</p>",
            agent_body_text="ответ",
            history_html=render_history_block(_msg(direction="inbound", text="вопрос")),
            history_plain="вопрос",
        )
        # Тени и скругления карточек отсутствуют (reply-маркер — единственное с
        # фоновой плашкой, это намеренно).
        body_html = html_out
        assert "box-shadow" not in body_html
        assert "border-radius:8px" not in body_html
