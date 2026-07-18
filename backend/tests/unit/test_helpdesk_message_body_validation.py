"""Unit-тесты ``_validate_message_body`` — валидация тела ответа.

Фикс бага: rich-редактор отправлял ответ из **только картинки** (``<img>`` без
текста), ``html_to_plain`` возвращал пустую строку → роутер возвращал
422 «Message body is empty», письмо не уходило. Теперь валидация принимает
сообщение, если есть plain **ИЛИ** html-контент — картинка без подписи
(скриншот ошибки) это нормальный кейс.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.helpdesk.tickets import _validate_message_body


class TestValidateMessageBody:
    def test_plain_text_accepted(self) -> None:
        """Есть plain-текст → валидно (не падает)."""
        _validate_message_body("ответ агентa", None)
        _validate_message_body(" текст ", "<p>текст</p>")

    def test_image_only_html_accepted(self) -> None:
        """Plain пустой, но есть html с картинкой → валидно.

        Это и есть баг-репорт: rich-редактор отправил ``<img>`` без текста,
        ``html_to_plain`` снял теги → пустая строка → старая проверка
        ``if not norm_text`` отбрасывала. Теперь принимаем.
        """
        html_with_image = (
            '<figure data-type="figure-image">'
            '<img src="/api/v1/helpdesk/tickets/abc/inline-media/img.png" alt=""/>'
            "<figcaption></figcaption>"
            "</figure>"
        )
        _validate_message_body("", html_with_image)

    def test_html_only_without_image_accepted(self) -> None:
        """Plain пустой, html с разметкой (не только img) → валидно."""
        _validate_message_body("", "<p><strong>жирный</strong> без plain-вывода</p>")

    def test_both_empty_rejected(self) -> None:
        """Пустой plain И пустой html → 422 (как раньше)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_message_body("", None)
        assert exc_info.value.status_code == 422
        assert "empty" in exc_info.value.detail.lower()

    def test_both_empty_string_rejected(self) -> None:
        """Пустые строки (не None) → 422 (защита: фронт прислал Form-поля, но без контента)."""
        with pytest.raises(HTTPException):
            _validate_message_body("", "")
