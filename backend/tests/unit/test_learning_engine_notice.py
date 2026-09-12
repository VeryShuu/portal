"""Unit: режимный маркер learning-движка (app/core/database.py).

Красный compose-smoke PR #161: лог-строка при импорте database.py попадала
в stdout ``alembic current`` раньше строки ревизии — парсер migrate.sh брал
дату вместо «107». Маркер обязан звучать один раз и только при первом
запросе learning-сессии, никогда — при импорте модуля."""

from __future__ import annotations

import pytest

from app.core import database


@pytest.fixture
def notice_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    calls: list[tuple[str, dict]] = []

    class _FakeLogger:
        def info(self, event: str, **kw) -> None:
            calls.append((event, kw))

        def warning(self, event: str, **kw) -> None:
            calls.append((event, kw))

    monkeypatch.setattr(database, "_learning_engine_notice_shown", False)
    monkeypatch.setattr(database, "logger", _FakeLogger())
    return calls


def test_notice_fires_once(monkeypatch: pytest.MonkeyPatch, notice_calls) -> None:
    monkeypatch.setattr(database.settings, "learning_db_password", None)
    database._notice_learning_engine()
    database._notice_learning_engine()
    database._notice_learning_engine()
    assert notice_calls == [
        (
            "learning.db_role_engine_disabled",
            {
                "hint": "LEARNING_DB_PASSWORD не задан — learning-роуты работают на общем движке",
            },
        )
    ]


def test_notice_enabled_branch(monkeypatch: pytest.MonkeyPatch, notice_calls) -> None:
    monkeypatch.setattr(database.settings, "learning_db_password", "secret")
    database._notice_learning_engine()
    assert notice_calls == [("learning.db_role_engine_enabled", {"role": "learning_app"})]
