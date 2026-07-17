"""Unit-тесты нормализации тела сообщения helpdesk (rich-редактор).

Проверяют ``normalize_message_bodies`` — sanitize HTML (nh3) + деривацию
``body_text`` (plain) из ``body_html``. Без БД — чистая функция.

Это критично для rich-редактора: фронт (TipTap) шлёт HTML, бэк обязан:
* срезать XSS (заявитель — неконтролируемая сторона);
* сохранить ``figure``/``figcaption``/``img`` (inline-картинки) и относительные
  URL (``/api/v1/helpdesk/.../inline-media/...``);
* деривировать ``body_text`` для email-треда (``text/plain`` часть письма).
"""

from __future__ import annotations

from app.services.helpdesk.messages import normalize_message_bodies


class TestNormalizeMessageBodies:
    def test_body_text_only_kept_as_is(self) -> None:
        """Plain-ответ (без HTML) — обратная совместимость: body_text как есть."""
        plain, html = normalize_message_bodies("Просто текст ответа", None)
        assert plain == "Просто текст ответа"
        assert html is None

    def test_html_only_derives_plain(self) -> None:
        """Rich-ответ (только HTML) — plain деривируется снятием тегов.

        ``html_to_plain`` заменяет каждый тег на пробел → между словами могут
        появиться сдвоенные пробелы (тег разбивает слово). Это ожидаемо и
        безопасно для email-треда (text/plain часть)."""
        plain, html = normalize_message_bodies(None, "<p>Привет <strong>мир</strong></p>")
        assert "Привет" in plain and "мир" in plain
        assert html == "<p>Привет <strong>мир</strong></p>"

    def test_both_present_prefers_explicit_body_text(self) -> None:
        """Если оба поля переданы — body_text имеет приоритет (явный plain)."""
        plain, html = normalize_message_bodies("Явный plain", "<p>HTML</p>")
        assert plain == "Явный plain"
        assert html == "<p>HTML</p>"

    def test_strips_xss_script(self) -> None:
        """XSS через <script> — nh3 срезает."""
        html_in = '<p>ok</p><script>alert(1)</script>'
        plain, html = normalize_message_bodies(None, html_in)
        assert "<script>" not in (html or "")
        assert "alert" not in (html or "")
        assert plain == "ok"

    def test_keeps_figure_figcaption_img(self) -> None:
        """Inline-картинка TipTap: figure+img+figcaption сохраняются."""
        html_in = (
            '<figure data-type="figure-image">'
            '<img src="/api/v1/helpdesk/tickets/abc/inline-media/x.png" alt="скрин" />'
            "<figcaption>Подпись</figcaption>"
            "</figure>"
            "<p>Текст ответа</p>"
        )
        _plain, html = normalize_message_bodies(None, html_in)
        assert html is not None
        assert "<figure" in html
        assert "<figcaption>Подпись</figcaption>" in html
        assert "<img" in html
        assert "inline-media/x.png" in html  # относительный URL сохранён
        # data-type может срезаться nh3 (нет в ALLOWED_ATTRS["*"]) — это ок для
        # режима чтения (HTML хранится, markdown нет).

    def test_strips_data_uri_in_img(self) -> None:
        """data: URI в img — небезопасен (data:text/html,<script>), nh3 срезает."""
        html_in = '<img src="data:text/html;base64,PHNjcmlwdD4=" alt="x">'
        _plain, html = normalize_message_bodies(None, html_in)
        assert "data:" not in (html or "")

    def test_empty_both_returns_empty(self) -> None:
        """Пустые оба поля → ('', None). Роутер валидирует непустоту (422)."""
        plain, html = normalize_message_bodies("", "")
        assert plain == ""
        assert html is None

    def test_none_both_returns_empty(self) -> None:
        plain, html = normalize_message_bodies(None, None)
        assert plain == ""
        assert html is None

    def test_empty_html_string_returns_none_html(self) -> None:
        """Пустая строка body_html → None (колонка nullable, не храним '')."""
        plain, html = normalize_message_bodies("текст", "")
        assert html is None
        assert plain == "текст"

    def test_strips_onerror_handler(self) -> None:
        """XSS через onerror — nh3 срезает атрибут."""
        html_in = '<img src="x" onerror="alert(1)" alt="x">'
        _plain, html = normalize_message_bodies(None, html_in)
        assert "onerror" not in (html or "")
        assert "alert" not in (html or "")

    def test_keeps_links(self) -> None:
        """Ссылки сохраняются (с http(s)/mailto schemes).

        nh3 добавляет ``rel="noopener noreferrer"`` к внешним ссылкам
        (safe-by-default) — это правильно, проверяем только href."""
        html_in = '<p>См. <a href="https://example.com">доку</a></p>'
        plain, html = normalize_message_bodies(None, html_in)
        assert 'href="https://example.com"' in (html or "")
        assert "noopener" in (html or "")
        assert "См." in plain and "доку" in plain
