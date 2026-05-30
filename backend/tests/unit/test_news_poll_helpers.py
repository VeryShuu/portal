from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace


def _make_user(role: str = "reader") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role=role, full_name="Test User", email="t@t.com")


def _make_poll(**kwargs) -> SimpleNamespace:
    p = SimpleNamespace()
    p.closed_at = kwargs.get("closed_at")
    p.closes_at = kwargs.get("closes_at")
    p.results_visibility = kwargs.get("results_visibility", "after_vote")
    return p


NOW = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


class TestIsPrivileged:
    def test_none_user(self):
        from app.services.news.poll._helpers import _is_privileged
        assert _is_privileged(None) is False

    def test_reader_not_privileged(self):
        from app.services.news.poll._helpers import _is_privileged
        assert _is_privileged(_make_user("reader")) is False

    def test_editor_is_privileged(self):
        from app.services.news.poll._helpers import _is_privileged
        assert _is_privileged(_make_user("editor")) is True

    def test_admin_is_privileged(self):
        from app.services.news.poll._helpers import _is_privileged
        assert _is_privileged(_make_user("admin")) is True


class TestAware:
    def test_already_aware(self):
        from app.services.news.poll._helpers import _aware
        dt = datetime(2024, 1, 1, tzinfo=UTC)
        assert _aware(dt) is dt

    def test_naive_gets_utc(self):
        from app.services.news.poll._helpers import _aware
        dt = datetime(2024, 1, 1)
        result = _aware(dt)
        assert result.tzinfo is UTC


class TestForbid:
    def test_returns_403(self):
        from app.services.news.poll._helpers import _forbid
        exc = _forbid("nope")
        assert exc.status_code == 403
        assert exc.detail == "nope"


class TestBad:
    def test_returns_400(self):
        from app.services.news.poll._helpers import _bad
        exc = _bad("bad request")
        assert exc.status_code == 400
        assert exc.detail == "bad request"


class TestIsPollClosed:
    def test_closed_at_set(self):
        from app.services.news.poll._helpers import is_poll_closed
        poll = _make_poll(closed_at=datetime(2023, 6, 1, tzinfo=UTC))
        assert is_poll_closed(poll, NOW) is True

    def test_closes_at_in_past(self):
        from app.services.news.poll._helpers import is_poll_closed
        poll = _make_poll(closes_at=datetime(2023, 12, 31, tzinfo=UTC))
        assert is_poll_closed(poll, NOW) is True

    def test_closes_at_in_future(self):
        from app.services.news.poll._helpers import is_poll_closed
        poll = _make_poll(closes_at=datetime(2025, 1, 1, tzinfo=UTC))
        assert is_poll_closed(poll, NOW) is False

    def test_neither_closed(self):
        from app.services.news.poll._helpers import is_poll_closed
        poll = _make_poll()
        assert is_poll_closed(poll, NOW) is False

    def test_closes_at_naive_in_past(self):
        from app.services.news.poll._helpers import is_poll_closed
        poll = _make_poll(closes_at=datetime(2023, 12, 31))
        assert is_poll_closed(poll, NOW) is True


class TestCanSeeResults:
    def test_privileged_always_sees(self):
        from app.services.news.poll._helpers import _can_see_results
        poll = _make_poll(results_visibility="only_admin_editor")
        assert _can_see_results(poll, _make_user("admin"), has_voted=False, is_closed=False) is True

    def test_only_admin_editor_reader_cannot(self):
        from app.services.news.poll._helpers import _can_see_results
        poll = _make_poll(results_visibility="only_admin_editor")
        assert _can_see_results(poll, _make_user("reader"), has_voted=True, is_closed=True) is False

    def test_always_visibility_reader(self):
        from app.services.news.poll._helpers import _can_see_results
        poll = _make_poll(results_visibility="always")
        assert _can_see_results(poll, _make_user("reader"), has_voted=False, is_closed=False) is True

    def test_after_vote_has_voted(self):
        from app.services.news.poll._helpers import _can_see_results
        poll = _make_poll(results_visibility="after_vote")
        assert _can_see_results(poll, None, has_voted=True, is_closed=False) is True

    def test_after_vote_not_voted(self):
        from app.services.news.poll._helpers import _can_see_results
        poll = _make_poll(results_visibility="after_vote")
        assert _can_see_results(poll, None, has_voted=False, is_closed=False) is False

    def test_after_close_is_closed(self):
        from app.services.news.poll._helpers import _can_see_results
        poll = _make_poll(results_visibility="after_close")
        assert _can_see_results(poll, None, has_voted=False, is_closed=True) is True

    def test_after_close_not_closed(self):
        from app.services.news.poll._helpers import _can_see_results
        poll = _make_poll(results_visibility="after_close")
        assert _can_see_results(poll, None, has_voted=False, is_closed=False) is False

    def test_unknown_visibility_returns_false(self):
        from app.services.news.poll._helpers import _can_see_results
        poll = _make_poll(results_visibility="unknown_value")
        assert _can_see_results(poll, None, has_voted=True, is_closed=True) is False

    def test_none_user_only_admin_editor(self):
        from app.services.news.poll._helpers import _can_see_results
        poll = _make_poll(results_visibility="only_admin_editor")
        assert _can_see_results(poll, None, has_voted=True, is_closed=True) is False
