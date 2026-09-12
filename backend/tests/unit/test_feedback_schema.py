"""Unit-тесты для Pydantic-схем модуля feedback (REVIEW-2.7).

Покрывают:
- `FeedbackIn` валидация `page_url` (относительный путь, абсолютный https,
  отказ на `http://`, `//host`, пустую строку, чрезмерную длину)
- `FeedbackIn` тримминг `message`, лимит длины
- `FeedbackReplyIn.message` — обязательное, тримминг, лимит длины
- `FeedbackStatusIn` — допустимые значения, отказ на произвольных
- StrEnum-значения `FeedbackCategory`/`FeedbackStatus`
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.feedback import (
    FeedbackCategory,
    FeedbackIn,
    FeedbackReplyIn,
    FeedbackStatus,
    FeedbackStatusIn,
)


class TestFeedbackInPageUrl:
    def test_none_allowed(self) -> None:
        fb = FeedbackIn(category=FeedbackCategory.bug, message="x", page_url=None)
        assert fb.page_url is None

    def test_blank_normalised_to_none(self) -> None:
        fb = FeedbackIn(category=FeedbackCategory.bug, message="x", page_url="   ")
        assert fb.page_url is None

    def test_relative_path_allowed(self) -> None:
        fb = FeedbackIn(category=FeedbackCategory.bug, message="x", page_url="/news/42")
        assert fb.page_url == "/news/42"

    def test_https_absolute_allowed(self) -> None:
        fb = FeedbackIn(
            category=FeedbackCategory.bug,
            message="x",
            page_url="https://portal.example/news/42",
        )
        assert fb.page_url == "https://portal.example/news/42"

    @pytest.mark.parametrize(
        "bad",
        [
            "http://portal.example/",
            "//attacker.example/",
            "javascript:alert(1)",
            "ftp://portal.example/",
            "x" * 2001,
        ],
    )
    def test_invalid_page_url_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            FeedbackIn(category=FeedbackCategory.bug, message="x", page_url=bad)


class TestFeedbackInMessage:
    def test_message_stripped(self) -> None:
        fb = FeedbackIn(category=FeedbackCategory.suggestion, message="  hi  ")
        assert fb.message == "hi"

    def test_message_empty_default(self) -> None:
        fb = FeedbackIn(category=FeedbackCategory.other)
        assert fb.message == ""

    def test_message_too_long(self) -> None:
        with pytest.raises(ValidationError):
            FeedbackIn(category=FeedbackCategory.bug, message="a" * 5001)


class TestFeedbackReplyIn:
    def test_strip(self) -> None:
        r = FeedbackReplyIn(message="  hello  ")
        assert r.message == "hello"

    def test_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FeedbackReplyIn(message="   ")

    def test_required(self) -> None:
        with pytest.raises(ValidationError):
            FeedbackReplyIn()  # type: ignore[call-arg]

    def test_too_long(self) -> None:
        with pytest.raises(ValidationError):
            FeedbackReplyIn(message="x" * 5001)


class TestFeedbackStatusIn:
    @pytest.mark.parametrize("status", ["open", "in_progress", "closed"])
    def test_valid(self, status: str) -> None:
        s = FeedbackStatusIn(status=status)  # type: ignore[arg-type]
        assert s.status.value == status

    @pytest.mark.parametrize("status", ["", "rejected", "deleted", "OPEN"])
    def test_invalid(self, status: str) -> None:
        with pytest.raises(ValidationError):
            FeedbackStatusIn(status=status)  # type: ignore[arg-type]


class TestEnumValues:
    def test_category_values(self) -> None:
        assert {c.value for c in FeedbackCategory} == {"bug", "suggestion", "other"}

    def test_status_values(self) -> None:
        assert {s.value for s in FeedbackStatus} == {"open", "in_progress", "closed"}
