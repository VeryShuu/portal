"""Unit-тесты отсечения цитируемых писем (``email_quote``).

Чистые функции — без БД и сети. Два слоя:
  1. Маркер-разделитель ``REPLY_MARKER_TOKEN`` в исходящих (build_reply_marker_*).
  2. Эвристический fallback для писем без маркера (strip_quoted_reply/html).

Покрывает: Outlook (From/Sent блок), Gmail EN/RU, -----Original Message-----,
наш собственный маркер, no-op для писем без цитаты, HTML quote-контейнеры.
"""

from __future__ import annotations

from app.services.helpdesk.email_quote import (
    REPLY_MARKER_TOKEN,
    build_reply_marker_html,
    build_reply_marker_plain,
    strip_quoted_html,
    strip_quoted_reply,
)

# ── build_reply_marker_* ─────────────────────────────────────────────────────


class TestBuildReplyMarker:
    def test_plain_contains_instruction_token_and_ticket(self) -> None:
        marker = build_reply_marker_plain(123)
        # REPLY_MARKER_TOKEN — это и есть видимая инструкция «Ответьте выше этой
        # линии» (видимый текст как якорь — надёжнее скрытого токена в Outlook).
        assert REPLY_MARKER_TOKEN in marker
        assert "TKT-123" in marker

    def test_plain_starts_with_newlines(self) -> None:
        # Маркер добавляется в конец body_text — отделяется пустыми строками.
        assert build_reply_marker_plain(1).startswith("\n\n")

    def test_html_contains_instruction_token_and_ticket(self) -> None:
        marker = build_reply_marker_html(123)
        assert REPLY_MARKER_TOKEN in marker
        assert "TKT-123" in marker

    def test_html_token_is_visible_text_no_hidden_div(self) -> None:
        # REPLY_MARKER_TOKEN — видимый текст плашки (↩ + фраза), скрытого div
        # с font-size:0 больше нет (он ненадёжно переживает ответ в Outlook).
        marker = build_reply_marker_html(42)
        assert REPLY_MARKER_TOKEN in marker
        assert "↩" in marker
        # Скрытых узлов быть не должно — токен виден как обычный текст.
        assert "font-size:0" not in marker
        assert "max-height:0" not in marker


# ── strip_quoted_reply — наш маркер ──────────────────────────────────────────


class TestStripQuotedReplyMarker:
    def test_our_marker_strips_quote_below(self) -> None:
        body = (
            "Спасибо, помогло!\n\n"
            + build_reply_marker_plain(123)
            + "\nПредыдущее письмо тут, его надо отрезать.\n"
        )
        assert strip_quoted_reply(body) == "Спасибо, помогло!"

    def test_marker_only_keeps_text_above(self) -> None:
        body = "Мой ответ\n" + build_reply_marker_plain(7) + "цитата"
        assert strip_quoted_reply(body) == "Мой ответ"

    def test_marker_in_html_form_token_still_works(self) -> None:
        # При деривации plain из html теги снимаются, токен остаётся текстом.
        # Токен стоит в начале строки блока — обрезка срабатывает.
        body = f"Ответ сверху\n--- {REPLY_MARKER_TOKEN} ---\nостальное отрезать"
        assert strip_quoted_reply(body) == "Ответ сверху"


# ── strip_quoted_reply — эвристика (без маркера) ─────────────────────────────


class TestStripQuotedReplyHeuristics:
    def test_outlook_en_from_sent_block(self) -> None:
        body = (
            "Да, всё работает, спасибо!\n"
            "From: Agent <agent@company.local>\n"
            "Sent: Tuesday, July 1, 2026 3:21 PM\n"
            "To: User <user@company.local>\n"
            "Subject: [#TKT-123] Не работает VPN\n"
            "\n"
            "Здравствуйте, проверьте настройки.\n"
        )
        assert strip_quoted_reply(body) == "Да, всё работает, спасибо!"

    def test_outlook_ru_ot_otpravleno_block(self) -> None:
        body = (
            "Получил, спасибо\n"
            "От: Агент <agent@company.local>\n"
            "Отправлено: 1 июля 2026 г. 15:21\n"
            "Кому: Пользователь <user@company.local>\n"
            "Тема: [#TKT-123] Не работает VPN\n"
            "\n"
            "Здравствуйте!\n"
        )
        assert strip_quoted_reply(body) == "Получил, спасибо"

    def test_gmail_en_on_wrote(self) -> None:
        body = (
            "Спасибо!\n\n"
            "On Tue, Jul 1, 2026 at 3:21 PM Agent <agent@company.local> wrote:\n"
            ">\n"
            "> Здравствуйте, проверьте настройки.\n"
        )
        assert strip_quoted_reply(body) == "Спасибо!"

    def test_gmail_ru_napisal(self) -> None:
        body = (
            "Ок\n\n"
            "1 июля 2026 г. в 15:21 Агент <agent@company.local> написал:\n"
            ">\n"
            "> Здравствуйте!\n"
        )
        assert strip_quoted_reply(body) == "Ок"

    def test_gmail_ru_napisala(self) -> None:
        # Женский род — «написала:»
        body = "Принято\n\n1 июля 2026 г. в 15:21 Агент <agent@company.local> написала:\n> текст"
        assert strip_quoted_reply(body) == "Принято"

    def test_original_message_en_dashes(self) -> None:
        body = (
            "Спасибо!\n"
            "-----Original Message-----\n"
            "From: Agent <agent@company.local>\n"
            "Здравствуйте!\n"
        )
        assert strip_quoted_reply(body) == "Спасибо!"

    def test_original_message_ru_dashes(self) -> None:
        body = (
            "Ок\n----- Исходное сообщение -----\nОт: Агент <agent@company.local>\nЗдравствуйте!\n"
        )
        assert strip_quoted_reply(body) == "Ок"

    def test_earliest_quote_block_wins(self) -> None:
        # Если несколько паттернов — режем по самому раннему.
        body = "Ответ\nOn Mon wrote:\n> первая цитата\n-----Original Message-----\nвторая цитата\n"
        assert strip_quoted_reply(body) == "Ответ"


# ── strip_quoted_reply — SOGo / Mail.ru-веб (регрессия прод-тикета) ──────────


class TestStripQuotedReplySogoMailRu:
    """SOGo / Mail.ru-веб (корпоративный webmail mail.mage.ru) формирует
    разделитель цитаты в виде ``<дата>, <отправитель> писал(а):`` (ru) или
    ``<date>, <sender> wrote:`` (en) — отличается от Gmail-ru отсутствием
    приставки «на-» (``писал`` vs ``написал``) и от Gmail-en отсутствием
    ведущего ``On``. Регрессия прод-тикета №60: ответы заявителя через SOGo
    сохранялись с неотрезанной историей переписки.
    """

    def test_sogo_ru_pisal_a(self) -> None:
        # Реальная строка из прод-тикета №60 (сообщение от Молчанова):
        # «Четверг, Август 06, 2026 15:21 MSK, it@mage.ru писал(а):»
        body = (
            "Ну дела, а как его загрузить?\n"
            "иконки у меня такой нет\n\n"
            "Четверг, Август 06, 2026 15:21 MSK, it@mage.ru писал(а):\n"
            " история переписки ниже\n"
        )
        assert strip_quoted_reply(body) == (
            "Ну дела, а как его загрузить?\nиконки у меня такой нет"
        )

    def test_sogo_ru_pisala(self) -> None:
        # Женский род без приставки «на-»: «писала:»
        body = "Принято\n\n1 июля 2026 г., Агент <a@b.test> писала:\n> текст"
        assert strip_quoted_reply(body) == "Принято"

    def test_sogo_ru_pisal(self) -> None:
        # Мужской род без приставки: «писал:»
        body = "Ок\n\nВчера, Агент <a@b.test> писал:\n> текст"
        assert strip_quoted_reply(body) == "Ок"

    def test_sogo_en_wrote_no_on_prefix(self) -> None:
        # SOGo EN: «<date>, <author> wrote:» — без ведущего «On» (как в Gmail).
        body = (
            "Thanks!\n\n"
            "Thursday, August 6, 2026 15:21 MSK, agent@x.test wrote:\n"
            "> previous message\n"
        )
        assert strip_quoted_reply(body) == "Thanks!"

    def test_word_pisal_in_legit_text_not_stripped(self) -> None:
        # Легитимный текст со словом «писал:» в середине обычной строки не
        # отрезается: паттерн требует двоеточие в КОНЦЕ строки (``:\s*$``) и
        # перевод строки перед разделителем (``^`` + ``re.M``).
        body = "Он писал мне вчера: важный текст на этой же строке"
        assert strip_quoted_reply(body) == body

    def test_pisal_divider_at_line_end_strips(self) -> None:
        # «писал:» в конце строки (после перевода) — это разделитель, отрезаем.
        body = "Ответ сверху\nОтправитель писал:\nцитата ниже"
        out = strip_quoted_reply(body)
        assert "Ответ сверху" in out
        assert "цитата ниже" not in out


# ── strip_quoted_reply — edge cases ──────────────────────────────────────────


class TestStripQuotedReplyEdgeCases:
    def test_no_quote_returns_unchanged(self) -> None:
        body = "Обычный ответ без цитаты.\nВторая строка."
        assert strip_quoted_reply(body) == body

    def test_empty_string(self) -> None:
        assert strip_quoted_reply("") == ""

    def test_only_whitespace(self) -> None:
        assert strip_quoted_reply("   \n  ") == "   \n  "

    def test_marked_block_at_very_start_keeps_text(self) -> None:
        # Если текст выше маркера пустой — возвращаем как есть (не теряем письмо).
        body = build_reply_marker_plain(1) + "цитата"
        assert strip_quoted_reply(body) == body

    def test_word_from_in_middle_not_stripped(self) -> None:
        # «From:» в середине обычного текста не должно ложно сработать —
        # паттерн требует перевода строки на Sent: сразу после.
        body = "I will reply from: home later."
        assert strip_quoted_reply(body) == body

    def test_trailing_dashes_not_stripped(self) -> None:
        # «-----» без «Original Message» — легитимный разделитель подписи.
        body = "Ответ\n-----\nПодпись"
        assert strip_quoted_reply(body) == body


# ── strip_quoted_html ──────────────────────────────────────────────────────────


class TestStripQuotedHtml:
    def test_our_marker_html_stripped(self) -> None:
        marker = build_reply_marker_html(5)
        html = "<p>Ответ</p>" + marker + "<p>цитата</p>"
        assert strip_quoted_html(html) == "<p>Ответ</p>"

    def test_gmail_quote_class_stripped(self) -> None:
        html = (
            "<p>Спасибо!</p>"
            '<div class="gmail_quote">'
            "<blockquote>Предыдущее письмо</blockquote>"
            "</div>"
        )
        assert strip_quoted_html(html) == "<p>Спасибо!</p>"

    def test_moz_cite_prefix_stripped(self) -> None:
        html = '<p>Ответ</p><blockquote class="moz-cite-prefix">цитата</blockquote>'
        assert strip_quoted_html(html) == "<p>Ответ</p>"

    def test_no_quote_class_returns_unchanged(self) -> None:
        # Универсальный <blockquote> без класса gmail_quote/moz-cite-prefix —
        # легитимное форматирование, НЕ трогаем.
        html = "<p>Ответ</p><blockquote>цитата как форматирование</blockquote>"
        assert strip_quoted_html(html) == html

    def test_empty_string(self) -> None:
        assert strip_quoted_html("") == ""


# ── strip_quoted_html — SOGo / Mail.ru-веб (регрессия прод-тикета) ──────────


class TestStripQuotedHtmlSogoMailRu:
    """SOGo (корпоративный webmail mail.mage.ru) оборачивает процитированное
    письмо в **голый** ``<blockquote>`` без классов ``gmail_quote``/``moz-cite-prefix``
    (поэтому слой ``_HTML_QUOTE_RE`` его пропускает), а над блоком ставит
    текст-разделитель «писал(а):»/«wrote:» внутри ``<p>``/``<div>``. Регрессия
    прод-тикета №60: цитата из-под голого ``<blockquote>`` не отрезалась.
    Новый слой ``_HTML_SOGO_HEADER_RE`` ловит разделитель и отрезает блок целиком.
    """

    def test_sogo_html_pisal_a_before_blockquote(self) -> None:
        # Реальная структура HTML из прод-тикета №60 (сообщение 3 Молчанова):
        # разделитель «писал(а):» внутри <p> + голый <blockquote> с историей.
        html = (
            "<p>Ну дела, а как его загрузить?&nbsp;<br>иконки у меня такой нет&nbsp;"
            "<br><br>Четверг, Август 06, 2026 15:21 MSK, it@mage.ru писал(а):"
            "<br><br>&nbsp;</p>"
            '<blockquote><div><figure class="table"><table><tbody><tr><td>'
            "<div><strong>#60 — СЭД</strong></div>"
            "<div>Сообщение от — Борзихин Вячеслав Сергеевич</div>"
            "</td></tr></tbody></table></figure></div></blockquote>"
        )
        out = strip_quoted_html(html)
        assert "Ну дела" in out
        assert "писал(а)" not in out
        assert "#60" not in out
        assert "Борзихин" not in out

    def test_sogo_html_wrote_before_blockquote(self) -> None:
        # EN-вариант: разделитель «wrote:» в отдельном <p> перед <blockquote>.
        html = (
            "<p>Thanks!</p>"
            "<p><br><br>Thursday, August 6, 2026 16:28 MSK, it@mage.ru wrote:"
            "<br><br>&nbsp;</p>"
            "<blockquote><div>#60 — history below</div></blockquote>"
        )
        out = strip_quoted_html(html)
        assert "Thanks!" in out
        assert "wrote" not in out
        assert "#60" not in out

    def test_bare_blockquote_without_sogo_header_not_stripped(self) -> None:
        # Регресс: голый <blockquote> без предшествующего разделителя НЕ трогается
        # (легитимное форматирование). ``_HTML_SOGO_HEADER_RE`` требует наличия
        # разделителя «писал(а):»/«wrote:» — без него отсечение не срабатывает.
        html = "<p>Ответ</p><blockquote>цитата как форматирование</blockquote>"
        assert strip_quoted_html(html) == html


# ── strip_quoted_html — Roundcube / Outlook-веб Original Message ────────────


class TestStripQuotedHtmlOriginalMessage:
    """Roundcube webmail оформляет процитированное письмо маркером
    ``-------- Исходное сообщение --------`` (ru) / ``-------- Original Message --------``
    (en) внутри ``<div>``/``<p>`` (без ``<b>`` и без quote-классов). Существующие
    слои ``_HTML_OUTLOOK_HEADER_RE`` (требует ``<b>From:</b>``) и ``_HTML_QUOTE_RE``
    (требует классы) его пропускали. Регрессия прод-тикета №72: ответы заявителя
    Баркова через Roundcube сохранялись с неотрезанной историей переписки.
    HTML-аналог первого ``_QUOTE_PATTERNS`` (plain) — ``_HTML_ORIGINAL_MESSAGE_RE``.
    """

    def test_roundcube_ru_original_message(self) -> None:
        # Реальная структура HTML из прод-тикета №72 (Roundcube, ответ Баркова):
        # «-------- Исходное сообщение --------» в <div> + история #72 ниже.
        html = (
            "<div>Так он мне сразу ошибку дает как клацаю на отсутствие</div>"
            "<div><br></div>"
            "<div><div>-------- Исходное сообщение --------</div>"
            "<div>От: it@mage.ru </div>"
            "<div>Дата: 07.08.2026  12:53  (GMT+03:00) </div>"
            "<div>Кому: boris.barkov@mage.ru </div>"
            "<div>Тема: [#TKT-72] СЭД </div></div>"
            "<div><table><tbody><tr><td><div>#72 — СЭД</div>"
            "<div><span>Сообщение от — </span>Борзихин</div>"
            "<div><p>попробуй написать меньше текста</p></div>"
            "</div></td></tr></tbody></table></div>"
        )
        out = strip_quoted_html(html)
        assert "Так он мне сразу ошибку" in out
        assert "Исходное сообщение" not in out
        assert "#72" not in out
        assert "Борзихин" not in out

    def test_roundcube_en_original_message(self) -> None:
        html = (
            "<div>My answer</div>"
            "<div>-------- Original Message --------</div>"
            "<div>From: agent@x.test</div>"
            "<div>history below</div>"
        )
        out = strip_quoted_html(html)
        assert "My answer" in out
        assert "Original Message" not in out
        assert "history below" not in out

    def test_legit_text_with_dashes_not_stripped(self) -> None:
        # Регресс: «---»/«-----» без «Original Message»/«Исходное сообщение» —
        # легитимный разделитель (например, подпись). Паттерн требует сигнатуру
        # forward-маркера, а не только дефисы.
        html = "<p>Обычный текст с --- тире посередине</p>"
        assert strip_quoted_html(html) == html

    def test_keep_forward_preserves_original_message_block(self) -> None:
        # ``keep_forward=True`` (новая заявка): forward-блок сохраняется, как и
        # для Gmail/Outlook/SOGo — для новой заявки forward может быть сутью
        # обращения (bounce/пересланный контекст проблемы).
        html = (
            "<p>Добрый день, не отправляется письмо.</p>"
            "<div>-------- Исходное сообщение --------</div>"
            "<div>From: Mailer-Daemon</div>"
            "<div>message size exceeds limit</div>"
        )
        out = strip_quoted_html(html, keep_forward=True)
        assert "Добрый день" in out
        assert "-------- Исходное сообщение --------" in out
        assert "message size exceeds limit" in out


# ── Round-trip: письмо с историей → ответ заявителя → чистый текст ────────────


class TestRoundTripWithHistory:
    """История переписки теперь включается в исходящее письмо **под**
    reply-маркером (``_try_enqueue_outbound`` → ``email_thread``). Эти тесты
    фиксируют гарантию: при ответе заявителя история (текст предшествующих
    сообщений) гарантированно отрезается маркером ``REPLY_MARKER_TOKEN`` и не
    попадает в ленту портала как часть ответа."""

    def test_history_under_marker_is_cut(self) -> None:
        import uuid
        from datetime import datetime
        from types import SimpleNamespace
        from typing import Any

        from app.services.helpdesk.email_thread import build_thread_history

        prior: Any = SimpleNamespace(
            id=uuid.uuid4(),
            body_text="Не работает VPN",
            body_html=None,
            direction="inbound",
            author_name="Заявитель",
            author_email="c@x.test",
            created_at=datetime(2026, 6, 30, 10, 0),
        )
        history_plain, _ = build_thread_history([prior], exclude_id=uuid.uuid4(), ticket_number=42)
        # Исходящее письмо: ответ + маркер + история.
        outbound = "Готово, исправили." + build_reply_marker_plain(42) + history_plain
        # История гарантированно отрезается маркером.
        assert "Не работает VPN" not in strip_quoted_reply(outbound)
        assert "Готово, исправили." in strip_quoted_reply(outbound)


# ── Outlook HTML: реальный регресс-кейс из продакшена ─────────────────────────


class TestOutlookHtmlRegressions:
    """Регрессии, обнаруженные на реальном письме Outlook (TKT-202):

    1. Outlook оборачивает ВСЁ письмо в ``<div class="WordSection1">`` — это
       контейнер письма, а не цитата. ``WordSection1`` не должен быть в списке
       quote-классов (отсечение от него режет от позиции 0 → нет эффекта).
    2. Outlook разбивает наш маркер ``<div class="portal-reply-marker">{TOKEN}
       </div>`` → класс теряется, текст-маркер оказывается в ``<div><p
       class="MsoNormal">{TOKEN}</p></div>``. Ищем по тексту-маркеру, а не по
       классу.
    3. Процитированный ответ агента стоит **выше** маркера, под Outlook
       quote-header ``<b><span>From:</span></b>``. Многослойная обрезка: маркер
       (отрезает историю) → Outlook header (отрезает процитированный ответ)."""

    def test_wordsection_not_treated_as_quote(self) -> None:
        """WordSection1 — контейнер письма, не цитата: легитимный текст внутри
        не должен обрезаться."""
        html = '<div class="WordSection1"><p>Легитимный ответ пользователя</p></div>'
        assert "Легитимный ответ пользователя" in strip_quoted_html(html)

    def test_outlook_broken_marker_still_cut(self) -> None:
        """Outlook разнёс маркер: фраза-якорь оказалась в ``<p class=MsoNormal>``
        без нашей обёртки. ``_OWN_MARKER_HTML_RE`` допускает обёртывающие теги
        перед видимой фразой-якорем — отсечение срабатывает."""
        html = (
            "<p>Ответ пользователя</p>"
            f'<div><p class="MsoNormal">{REPLY_MARKER_TOKEN}</p></div>'
            "<div>История заявки</div>"
        )
        out = strip_quoted_html(html)
        assert "Ответ пользователя" in out
        assert REPLY_MARKER_TOKEN not in out
        assert "История заявки" not in out

    def test_outlook_quote_header_cuts_cited_reply(self) -> None:
        """Outlook quote-header ``<b><span>From:</span></b>`` — отрезает
        процитированный ответ агента (над маркером)."""
        html = (
            "<p>Ответ пользователя</p>"
            "<div><p><b><span>From:</span></b><span> portal@x.test</span></p></div>"
            "<p>Процитированный ответ агента</p>"
        )
        out = strip_quoted_html(html)
        assert "Ответ пользователя" in out
        assert "Процитированный ответ агента" not in out

    def test_real_outlook_email_full_roundtrip(self) -> None:
        """Полный HTML реального письма: ответ + Outlook header + процитированный
        ответ агента + маркер + история. Должен остаться только ответ пользователя."""
        html = (
            '<div class="WordSection1">'
            '<p class="MsoNormal"><span>Точно ли труньк?</span></p>'
            '<p class="MsoNormal"><span>&nbsp;</span></p>'
            '<div><p class="MsoNormal"><b><span>From:</span></b>'
            "<span> portal@mage.ru <br><b>Sent:</b> Thursday<br>"
            "<b>Subject:</b> [#TKT-202]</span></p></div>"
            "<pre>ага да очень труньк</pre>"
            '<div><p class="MsoNormal">portal-helpdesk-reply-marker</p></div>'
            '<div class="MsoNormal"><hr></div>'
            '<p class="MsoNormal"><em><span>Ответьте выше этой строки</span></em></p>'
            '<div><p class="MsoNormal"><span>История заявки</span></p></div>'
            "</div>"
        )
        out = strip_quoted_html(html)
        assert "Точно ли труньк?" in out
        # Процитированный ответ агента и история — отрезаны.
        assert "ага да очень труньк" not in out
        assert "История заявки" not in out
        assert REPLY_MARKER_TOKEN not in out


# ── keep_forward=True (новые заявки) ─────────────────────────────────────────


class TestStripQuotedKeepForward:
    """``keep_forward=True``: forward-блок не отрезается (новая заявка).

    Для новой заявки forward — часто суть обращения (bounce об ошибке доставки,
    пересланный контекст проблемы), а не цитата. Маркер ``REPLY_MARKER_TOKEN``
    режется всегда — он проставляется только исходящими письмами портала.
    """

    # ── plain ──────────────────────────────────────────────────────────────────

    def test_plain_keeps_original_message_block(self) -> None:
        """``-----Original Message-----`` (forward) сохраняется при keep_forward."""
        body = (
            "Добрый день, не отправляется письмо.\n\n"
            "-----Original Message-----\n"
            "From: Mailer-Daemon\n"
            "message size exceeds limit\n"
        )
        out = strip_quoted_reply(body, keep_forward=True)
        assert "Добрый день" in out
        # Forward-блок сохранён целиком.
        assert "-----Original Message-----" in out
        assert "message size exceeds limit" in out

    def test_plain_keeps_outlook_from_sent_block(self) -> None:
        """Outlook ``From:``/``Sent:`` (forward) сохраняется при keep_forward."""
        body = (
            "Добрый день.\n\n"
            "From: Pantina <pantina.ea@mage.ru>\n"
            "Sent: Friday\n"
            "To: support\n"
            "Subject: Test\n\n"
            "Пересланное сообщение\n"
        )
        out = strip_quoted_reply(body, keep_forward=True)
        assert "Добрый день." in out
        assert "Пересланное сообщение" in out
        assert "From: Pantina" in out

    def test_plain_keeps_gmail_wrote_block(self) -> None:
        """Gmail ``On … wrote:`` (forward) сохраняется при keep_forward."""
        body = "Смотрите вложение.\n\nOn Fri, Jul 31 2026, Ivan wrote:\n> предыдущее сообщение\n"
        out = strip_quoted_reply(body, keep_forward=True)
        assert "Смотрите вложение." in out
        assert "предыдущее сообщение" in out

    def test_plain_still_cuts_own_marker_even_with_keep_forward(self) -> None:
        """Маркер ``REPLY_MARKER_TOKEN`` режется даже при keep_forward: он
        проставляется только исходящими письмами портала → заявитель отвечает
        на наш тикет, цитату убрать. ``keep_forward`` не должен маскировать
        пропуск forward-блока под видом новой заявки при наличии маркера."""
        body = "Спасибо!\n\n" + build_reply_marker_plain(42) + "\nЦитата предыдущего письма\n"
        out = strip_quoted_reply(body, keep_forward=True)
        assert "Спасибо!" in out
        assert "Цитата предыдущего письма" not in out
        assert REPLY_MARKER_TOKEN not in out

    def test_plain_default_strips_forward(self) -> None:
        """Без keep_forward (ответ на тикет) forward режется как цитата."""
        body = "Спасибо.\n\n-----Original Message-----\nFrom: a@b\nпредыдущее\n"
        out = strip_quoted_reply(body)  # keep_forward=False (дефолт)
        assert "Спасибо." in out
        assert "предыдущее" not in out

    # ── html ───────────────────────────────────────────────────────────────────

    def test_html_keeps_outlook_from_header(self) -> None:
        """Outlook ``<b>From:</b>`` header сохраняется при keep_forward."""
        html = (
            "<p>Добрый день.</p>"
            "<div><p><b><span>From:</span></b><span> Mailer-Daemon</span></p></div>"
            "<p>message size exceeds limit</p>"
        )
        out = strip_quoted_html(html, keep_forward=True)
        assert "Добрый день." in out
        assert "message size exceeds limit" in out
        assert "From:" in out

    def test_html_keeps_gmail_quote_container(self) -> None:
        """``gmail_quote``-контейнер сохраняется при keep_forward."""
        html = '<p>Смотрите ниже.</p><div class="gmail_quote"><p>Пересланное сообщение</p></div>'
        out = strip_quoted_html(html, keep_forward=True)
        assert "Смотрите ниже." in out
        assert "Пересланное сообщение" in out

    def test_html_still_cuts_own_marker_even_with_keep_forward(self) -> None:
        """Маркер режется даже при keep_forward (см. plain-аналог)."""
        html = (
            "<p>Ответ</p>"
            f'<div><p class="MsoNormal">{REPLY_MARKER_TOKEN}</p></div>'
            "<div>История</div>"
        )
        out = strip_quoted_html(html, keep_forward=True)
        assert "Ответ" in out
        assert "История" not in out
        assert REPLY_MARKER_TOKEN not in out

    def test_html_default_strips_forward(self) -> None:
        """Без keep_forward Outlook header режется (ответ на тикет)."""
        html = (
            "<p>Ответ.</p>"
            "<div><p><b><span>From:</span></b><span> portal@x</span></p></div>"
            "<p>Процитированный ответ</p>"
        )
        out = strip_quoted_html(html)  # keep_forward=False (дефолт)
        assert "Ответ." in out
        assert "Процитированный ответ" not in out

    # ── SOGo / Mail.ru-веб при keep_forward (новая заявка — forward) ───────────

    def test_plain_keeps_sogo_pisal_block(self) -> None:
        """SOGo «писал(а):» (forward) сохраняется при keep_forward=True — для
        новой заявки forward-блок может быть сутью обращения (как Gmail/Outlook)."""
        body = (
            "Смотрите ниже.\n\n"
            "Понедельник, Август 06, 2026, sender@x.test писал(а):\n"
            "> пересланное сообщение\n"
        )
        out = strip_quoted_reply(body, keep_forward=True)
        assert "Смотрите ниже." in out
        assert "пересланное сообщение" in out
        assert "писал(а)" in out

    def test_html_keeps_sogo_header(self) -> None:
        """HTML-разделитель SOGo «писал(а):» + <blockquote> сохраняется при
        keep_forward=True (новая заявка — forward может быть сутью обращения)."""
        html = (
            "<p>Смотрите ниже.</p>"
            "<p>Отправитель писал(а):<br>&nbsp;</p>"
            "<blockquote><p>Пересланное сообщение</p></blockquote>"
        )
        out = strip_quoted_html(html, keep_forward=True)
        assert "Смотрите ниже." in out
        assert "Пересланное сообщение" in out
