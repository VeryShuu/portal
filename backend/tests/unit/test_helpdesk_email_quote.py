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
        assert "Ответьте выше этой строки" in marker
        assert REPLY_MARKER_TOKEN in marker
        assert "TKT-123" in marker

    def test_plain_starts_with_newlines(self) -> None:
        # Маркер добавляется в конец body_text — отделяется пустыми строками.
        assert build_reply_marker_plain(1).startswith("\n\n")

    def test_html_contains_instruction_token_and_ticket(self) -> None:
        marker = build_reply_marker_html(123)
        assert "Ответьте выше этой строки" in marker
        assert REPLY_MARKER_TOKEN in marker
        assert "TKT-123" in marker
        assert "portal-reply-marker" in marker

    def test_html_uses_div_first_then_hr(self) -> None:
        # div.portal-reply-marker (с токеном) идёт первым — чтобы strip_quoted_html
        # резал от него вместе с предшествующим <hr>, не оставляя висячего разделителя.
        marker = build_reply_marker_html(42)
        assert marker.startswith('<div class="portal-reply-marker">')
        assert "<hr>" in marker


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
        body = (
            "Ответ сверху\n"
            f"--- {REPLY_MARKER_TOKEN} ---\n"
            "остальное отрезать"
        )
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
        body = (
            "Принято\n\n"
            "1 июля 2026 г. в 15:21 Агент <agent@company.local> написала:\n"
            "> текст"
        )
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
            "Ок\n"
            "----- Исходное сообщение -----\n"
            "От: Агент <agent@company.local>\n"
            "Здравствуйте!\n"
        )
        assert strip_quoted_reply(body) == "Ок"

    def test_earliest_quote_block_wins(self) -> None:
        # Если несколько паттернов — режем по самому раннему.
        body = (
            "Ответ\n"
            "On Mon wrote:\n"
            "> первая цитата\n"
            "-----Original Message-----\n"
            "вторая цитата\n"
        )
        assert strip_quoted_reply(body) == "Ответ"


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
            '<p>Спасибо!</p>'
            '<div class="gmail_quote">'
            '<blockquote>Предыдущее письмо</blockquote>'
            '</div>'
        )
        assert strip_quoted_html(html) == "<p>Спасибо!</p>"

    def test_moz_cite_prefix_stripped(self) -> None:
        html = (
            '<p>Ответ</p>'
            '<blockquote class="moz-cite-prefix">цитата</blockquote>'
        )
        assert strip_quoted_html(html) == "<p>Ответ</p>"

    def test_no_quote_class_returns_unchanged(self) -> None:
        # Универсальный <blockquote> без класса gmail_quote/moz-cite-prefix —
        # легитимное форматирование, НЕ трогаем.
        html = "<p>Ответ</p><blockquote>цитата как форматирование</blockquote>"
        assert strip_quoted_html(html) == html

    def test_empty_string(self) -> None:
        assert strip_quoted_html("") == ""


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

        from app.services.helpdesk.email_thread import build_thread_history

        prior = SimpleNamespace(
            id=uuid.uuid4(),
            body_text="Не работает VPN",
            body_html=None,
            direction="inbound",
            visibility="public",
            author_name="Заявитель",
            author_email="c@x.test",
            created_at=datetime(2026, 6, 30, 10, 0),
        )
        history_plain, _ = build_thread_history(
            [prior], exclude_id=uuid.uuid4(), ticket_number=42
        )
        # Исходящее письмо: ответ + маркер + история.
        outbound = "Готово, исправили." + build_reply_marker_plain(42) + history_plain
        # История гарантированно отрезается маркером.
        assert "Не работает VPN" not in strip_quoted_reply(outbound)
        assert "Готово, исправили." in strip_quoted_reply(outbound)
