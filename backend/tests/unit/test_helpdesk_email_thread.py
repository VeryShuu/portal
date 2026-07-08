"""Unit-тесты сборки истории переписки для исходящего письма (``email_thread``).

Чистые функции на заглушках-объектах (без БД) — образец ``test_helpdesk_email_quote``.

Покрывает: пустая история (первый ответ), одно/несколько сообщений, исключение
текущего ответа, отсев internal-заметок, лимит HISTORY_MAX_MESSAGES, escaping
пользовательских данных, структуру plain/html.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.helpdesk.email_thread import (
    HISTORY_MAX_MESSAGES,
    build_thread_history,
)


def _msg(
    *,
    text: str = "Текст сообщения",
    html: str | None = None,
    direction: str = "inbound",
    visibility: str = "public",
    author_name: str = "Иван Петров",
    author_email: str = "ivan@example.com",
    created_at: datetime | None = None,
) -> SimpleNamespace:
    """Заглушка сообщения (duck-typing — нужны только атрибуты, читаемые
    ``email_thread``)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        body_text=text,
        body_html=html,
        direction=direction,
        visibility=visibility,
        author_name=author_name,
        author_email=author_email,
        created_at=created_at or datetime(2026, 7, 1, 10, 0),
    )


# ── Пустая история ───────────────────────────────────────────────────────────


class TestEmptyHistory:
    def test_no_prior_messages_returns_empty(self) -> None:
        """Первый ответ агента — предшественников нет (только сам текущий ответ,
        который исключается)."""
        current = _msg(direction="outbound")
        plain, html = build_thread_history([current], exclude_id=current.id, ticket_number=5)
        assert plain == ""
        assert html == ""

    def test_only_internal_notes_excluded(self) -> None:
        """Internal-заметки не попадают в историю (заявитель их не видит)."""
        note = _msg(visibility="internal", text="Внутренняя заметка")
        plain, html = build_thread_history([note], exclude_id=uuid.uuid4(), ticket_number=5)
        assert plain == ""
        assert html == ""


# ── Структура plain ──────────────────────────────────────────────────────────


class TestPlainStructure:
    def test_header_with_ticket_number(self) -> None:
        m = _msg(direction="inbound")
        plain, _ = build_thread_history([m], exclude_id=uuid.uuid4(), ticket_number=42)
        assert "=== История заявки [#TKT-42] ===" in plain

    def test_message_block_quote_format(self) -> None:
        """Plain-блок: «От {name}, {date}:» + строки с ``>``-префиксом.

        Время конвертируется в портала-tz (default Europe/Moscow, UTC+3):
        naive ``14:30`` считается UTC → ``17:30 MSK``."""
        m = _msg(
            text="Первая строка\nВторая строка",
            author_name="Анна Смирнова",
            created_at=datetime(2026, 6, 30, 14, 30),
        )
        plain, _ = build_thread_history([m], exclude_id=uuid.uuid4(), ticket_number=1)
        assert "От Анна Смирнова, 30.06.2026 17:30:" in plain
        assert "> Первая строка" in plain
        assert "> Вторая строка" in plain

    def test_display_name_falls_back_to_email(self) -> None:
        m = _msg(author_name=None, author_email="guest@x.test")
        plain, _ = build_thread_history([m], exclude_id=uuid.uuid4(), ticket_number=1)
        assert "От guest@x.test" in plain


# ── Структура html ───────────────────────────────────────────────────────────
# HTML-блоки истории рендерит ``email_template.render_history_block`` (alternating-
# фон + бейджи ролей «Заявитель»/«Специалист»). Тесты этой структуры — в
# ``test_helpdesk_email_template.py::TestRenderHistoryBlock``. Здесь проверяем,
# что ``build_thread_history`` делегирует HTML в шаблон (а не рендерит сам).


class TestHtmlDelegation:
    def test_html_uses_body_html_when_present(self) -> None:
        m = _msg(text="plain fallback", html="<p>HTML body</p>")
        _, html = build_thread_history([m], exclude_id=uuid.uuid4(), ticket_number=1)
        assert "<p>HTML body</p>" in html

    def test_html_has_role_badges(self) -> None:
        """Шаблон ставит бейджи «Заявитель»/«Специалист» вместо стрелок."""
        inbound = _msg(direction="inbound", created_at=datetime(2026, 7, 1, 9, 0))
        outbound = _msg(direction="outbound", created_at=datetime(2026, 7, 1, 9, 5))
        _, html = build_thread_history(
            [inbound, outbound], exclude_id=uuid.uuid4(), ticket_number=1
        )
        assert "Заявитель" in html
        assert "Специалист" in html


# ── Исключение текущего сообщения + порядок ──────────────────────────────────


class TestExcludeAndOrder:
    def test_current_message_excluded(self) -> None:
        current = _msg(text="ТЕКУЩИЙ ОТВЕТ", direction="outbound")
        prior = _msg(text="Предыдущее сообщение", direction="inbound")
        plain, _ = build_thread_history(
            [current, prior], exclude_id=current.id, ticket_number=1
        )
        assert "ТЕКУЩИЙ ОТВЕТ" not in plain
        assert "Предыдущее сообщение" in plain

    def test_reverse_chronological_order(self) -> None:
        """История строится в обратном порядке (новые → старые): ответ агента
        вверху письма, под разделителем — ближайшее предшествующее сообщение,
        самое старое внизу. Continuity «ответ → назад во времени» (Zammad/Freshdesk),
        независимо от порядка в исходном списке."""
        older = _msg(text="СТАРОЕ", created_at=datetime(2026, 6, 1, 10, 0))
        newer = _msg(text="НОВОЕ", created_at=datetime(2026, 6, 2, 10, 0))
        plain, _ = build_thread_history(
            [older, newer], exclude_id=uuid.uuid4(), ticket_number=1
        )
        assert plain.index("НОВОЕ") < plain.index("СТАРОЕ")


# ── Лимит ────────────────────────────────────────────────────────────────────


class TestLimit:
    def test_caps_at_max_messages(self) -> None:
        """При превышении HISTORY_MAX_MESSAGES берётся хвост (самые свежие)."""
        msgs = [
            _msg(text=f"msg-{i}", created_at=datetime(2026, 1, 1) + timedelta(days=i))
            for i in range(HISTORY_MAX_MESSAGES + 5)
        ]
        plain, _ = build_thread_history(msgs, exclude_id=uuid.uuid4(), ticket_number=1)
        # Самое старое отброшено, в истории виден хвост.
        assert "msg-0" not in plain
        assert f"msg-{HISTORY_MAX_MESSAGES + 4}" in plain
        # Точное число блоков-цитат = HISTORY_MAX_MESSAGES (заголовок не считается).
        quote_lines = [ln for ln in plain.splitlines() if ln.startswith("> msg-")]
        assert len(quote_lines) == HISTORY_MAX_MESSAGES


# ── Escaping ─────────────────────────────────────────────────────────────────


class TestEscaping:
    def test_user_data_escaped_in_html(self) -> None:
        """Имя автора и текст экранируются от HTML-инъекций."""
        m = _msg(
            author_name="<script>x</script>",
            text="plain",
            html=None,  # чтобы тело шло через <pre> с escape
        )
        _, html = build_thread_history([m], exclude_id=uuid.uuid4(), ticket_number=1)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
