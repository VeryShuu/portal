"""Unit-тесты напоминаний о дедлайне (этап 2, §15): письмо (текст + HTML)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.learning.emails import deadline_reminder_letter


def test_letter_contains_deadline_remaining_and_link():
    subject, body, html = deadline_reminder_letter(
        full_name="Иван Иванов",
        course_title="Охрана труда",
        deadline_at=datetime(2026, 9, 5, 18, 0, tzinfo=UTC),
        remaining=2,
        link="https://portal.example.org/learning/courses/ohrana-truda",
    )
    assert "Охрана труда" in subject and "05.09.2026" in subject
    assert "Иван Иванов" in body
    assert "05.09.2026" in body
    assert "2" in body
    assert "https://portal.example.org/learning/courses/ohrana-truda" in body
    # HTML-часть обязательна: пустой html в Outlook выглядит как пустое письмо
    # (прод-кейс 2026-09-03); ссылка — кликабельная и экранированная.
    assert html.strip()
    assert 'href="https://portal.example.org/learning/courses/ohrana-truda"' in html
    assert "Иван Иванов" in html and "05.09.2026" in html
