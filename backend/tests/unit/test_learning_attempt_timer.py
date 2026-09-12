"""Unit-тесты таймера попытки (этап 2, §15): абсолютный край попытки."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.learning.tests_service import attempt_expires_at


def _attempt(started: datetime) -> SimpleNamespace:
    return SimpleNamespace(started_at=started)


def _test(limit_minutes: int | None) -> SimpleNamespace:
    return SimpleNamespace(time_limit_minutes=limit_minutes)


class TestAttemptExpiresAt:
    def test_no_limit_returns_none(self):
        started = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
        assert attempt_expires_at(_test(None), _attempt(started)) is None

    def test_limit_adds_minutes(self):
        started = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
        expires = attempt_expires_at(_test(45), _attempt(started))
        assert expires == started + timedelta(minutes=45)
