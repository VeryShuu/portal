"""Unit tests for the recurrence expansion service."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest


def _rule(freq: str, until: date):
    from app.schemas.meetings import RecurrenceRule

    return RecurrenceRule(freq=freq, until_date=until)


class TestExpandRecurrence:
    def test_daily_generates_consecutive_days(self):
        from app.services.meetings.recurrence import expand_recurrence

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        end = datetime(2030, 1, 1, 11, 0, tzinfo=UTC)
        rule = _rule("DAILY", date(2030, 1, 5))
        instances = expand_recurrence(start, end, rule, tz="UTC")
        assert len(instances) == 5
        assert instances[0][0] == start
        assert all((e - s).total_seconds() == 3600 for s, e in instances)

    def test_weekdays_skips_weekend(self):
        from app.services.meetings.recurrence import expand_recurrence

        # 2030-01-04 is a Friday
        start = datetime(2030, 1, 4, 9, 0, tzinfo=UTC)
        end = datetime(2030, 1, 4, 10, 0, tzinfo=UTC)
        rule = _rule("WEEKDAYS", date(2030, 1, 8))
        instances = expand_recurrence(start, end, rule, tz="UTC")
        weekdays = {s.weekday() for s, _ in instances}
        assert weekdays.issubset({0, 1, 2, 3, 4})

    def test_weekly_picks_same_weekday(self):
        from app.services.meetings.recurrence import expand_recurrence

        start = datetime(2030, 1, 2, 10, 0, tzinfo=UTC)  # Wed
        end = datetime(2030, 1, 2, 11, 0, tzinfo=UTC)
        rule = _rule("WEEKLY", date(2030, 1, 31))
        instances = expand_recurrence(start, end, rule, tz="UTC")
        assert len(instances) == 5  # 5 wednesdays
        assert all(s.weekday() == 2 for s, _ in instances)

    def test_biweekly_two_week_gap(self):
        from app.services.meetings.recurrence import expand_recurrence

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        end = datetime(2030, 1, 1, 11, 0, tzinfo=UTC)
        rule = _rule("BIWEEKLY", date(2030, 2, 28))
        instances = expand_recurrence(start, end, rule, tz="UTC")
        assert len(instances) >= 2
        gap = (instances[1][0] - instances[0][0]).days
        assert gap == 14

    def test_monthly_keeps_day_of_month(self):
        from app.services.meetings.recurrence import expand_recurrence

        start = datetime(2030, 1, 15, 10, 0, tzinfo=UTC)
        end = datetime(2030, 1, 15, 11, 0, tzinfo=UTC)
        rule = _rule("MONTHLY", date(2030, 6, 30))
        instances = expand_recurrence(start, end, rule, tz="UTC")
        assert len(instances) == 6
        assert all(s.day == 15 for s, _ in instances)

    def test_monthly_rejects_day_above_28(self):
        from app.services.meetings.recurrence import expand_recurrence

        start = datetime(2030, 1, 30, 10, 0, tzinfo=UTC)
        end = datetime(2030, 1, 30, 11, 0, tzinfo=UTC)
        rule = _rule("MONTHLY", date(2030, 12, 31))
        with pytest.raises(ValueError):
            expand_recurrence(start, end, rule, tz="UTC")

    def test_too_many_instances_rejected(self):
        from app.services.meetings.recurrence import expand_recurrence

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        end = datetime(2030, 1, 1, 11, 0, tzinfo=UTC)
        rule = _rule("DAILY", date(2030, 3, 31))  # ~90 instances
        with pytest.raises(ValueError):
            expand_recurrence(start, end, rule, tz="UTC")


class TestBuildRruleString:
    def test_daily(self):
        from app.services.meetings.recurrence import build_rrule_string

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        s = build_rrule_string(_rule("DAILY", date(2030, 1, 31)), start)
        assert s.startswith("FREQ=DAILY;UNTIL=20300131T235959Z")

    def test_weekdays_byday(self):
        from app.services.meetings.recurrence import build_rrule_string

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        s = build_rrule_string(_rule("WEEKDAYS", date(2030, 1, 31)), start)
        assert "BYDAY=MO,TU,WE,TH,FR" in s

    def test_weekly_uses_start_weekday(self):
        from app.services.meetings.recurrence import build_rrule_string

        start = datetime(2030, 1, 2, 10, 0, tzinfo=UTC)  # Wed
        s = build_rrule_string(_rule("WEEKLY", date(2030, 1, 31)), start)
        assert "BYDAY=WE" in s

    def test_biweekly_interval_2(self):
        from app.services.meetings.recurrence import build_rrule_string

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        s = build_rrule_string(_rule("BIWEEKLY", date(2030, 2, 28)), start)
        assert "INTERVAL=2" in s

    def test_monthly_bymonthday(self):
        from app.services.meetings.recurrence import build_rrule_string

        start = datetime(2030, 1, 15, 10, 0, tzinfo=UTC)
        s = build_rrule_string(_rule("MONTHLY", date(2030, 6, 30)), start)
        assert "BYMONTHDAY=15" in s
