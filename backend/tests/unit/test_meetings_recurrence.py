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

    def test_unknown_freq_raises(self):
        from app.schemas.meetings import RecurrenceRule
        from app.services.meetings.recurrence import build_rrule_string

        rule = RecurrenceRule(freq="DAILY", until_date=date(2030, 1, 31))
        rule.freq = "UNKNOWN"
        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        with pytest.raises(ValueError):
            build_rrule_string(rule, start)

    def test_invalid_tz_falls_back_to_utc(self):
        from app.services.meetings.recurrence import build_rrule_string

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        s = build_rrule_string(_rule("DAILY", date(2030, 1, 31)), start, tz="Invalid/TZ")
        assert "FREQ=DAILY" in s

    def test_naive_start_treated_as_utc(self):
        from app.services.meetings.recurrence import build_rrule_string

        start = datetime(2030, 1, 15, 10, 0)
        s = build_rrule_string(_rule("MONTHLY", date(2030, 6, 30)), start)
        assert "BYMONTHDAY=15" in s


class TestParseRruleString:
    def test_parse_daily(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("FREQ=DAILY;UNTIL=20300131T235959Z")
        assert result is not None
        assert result.freq == "DAILY"
        assert result.until_date.year == 2030
        assert result.until_date.month == 1
        assert result.until_date.day == 31

    def test_parse_weekdays(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=20300131T235959Z")
        assert result is not None
        assert result.freq == "WEEKDAYS"

    def test_parse_biweekly(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("FREQ=WEEKLY;INTERVAL=2;BYDAY=WE;UNTIL=20300228T235959Z")
        assert result is not None
        assert result.freq == "BIWEEKLY"

    def test_parse_weekly(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("FREQ=WEEKLY;BYDAY=WE;UNTIL=20300131T235959Z")
        assert result is not None
        assert result.freq == "WEEKLY"

    def test_parse_monthly(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("FREQ=MONTHLY;BYMONTHDAY=15;UNTIL=20300630T235959Z")
        assert result is not None
        assert result.freq == "MONTHLY"

    def test_missing_freq_returns_none(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("UNTIL=20300131T235959Z")
        assert result is None

    def test_missing_until_returns_none(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("FREQ=DAILY")
        assert result is None

    def test_empty_string_returns_none(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("")
        assert result is None

    def test_invalid_until_date_returns_none(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("FREQ=DAILY;UNTIL=BADDATE")
        assert result is None

    def test_unknown_freq_returns_none(self):
        from app.services.meetings.recurrence import parse_rrule_string

        result = parse_rrule_string("FREQ=HOURLY;UNTIL=20300131T235959Z")
        assert result is None

    def test_roundtrip_daily(self):
        from app.services.meetings.recurrence import build_rrule_string, parse_rrule_string

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        original = _rule("DAILY", date(2030, 1, 31))
        rrule_str = build_rrule_string(original, start)
        parsed = parse_rrule_string(rrule_str)
        assert parsed is not None
        assert parsed.freq == original.freq

    def test_roundtrip_weekly(self):
        from app.services.meetings.recurrence import build_rrule_string, parse_rrule_string

        start = datetime(2030, 1, 2, 10, 0, tzinfo=UTC)
        original = _rule("WEEKLY", date(2030, 1, 31))
        rrule_str = build_rrule_string(original, start)
        parsed = parse_rrule_string(rrule_str)
        assert parsed is not None
        assert parsed.freq == original.freq


class TestExpandRecurrenceEdgeCases:
    def test_invalid_tz_falls_back_to_utc(self):
        from app.services.meetings.recurrence import expand_recurrence

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        end = datetime(2030, 1, 1, 11, 0, tzinfo=UTC)
        rule = _rule("DAILY", date(2030, 1, 3))
        instances = expand_recurrence(start, end, rule, tz="Invalid/TZ")
        assert len(instances) == 3

    def test_unknown_freq_raises(self):
        from app.schemas.meetings import RecurrenceRule
        from app.services.meetings.recurrence import expand_recurrence

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        end = datetime(2030, 1, 1, 11, 0, tzinfo=UTC)
        rule = RecurrenceRule(freq="DAILY", until_date=date(2030, 1, 31))
        rule.freq = "UNKNOWN"
        with pytest.raises(ValueError):
            expand_recurrence(start, end, rule, tz="UTC")

    def test_duration_preserved_across_instances(self):
        from app.services.meetings.recurrence import expand_recurrence

        start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
        end = datetime(2030, 1, 1, 12, 30, tzinfo=UTC)
        rule = _rule("DAILY", date(2030, 1, 3))
        instances = expand_recurrence(start, end, rule, tz="UTC")
        for s, e in instances:
            assert (e - s).total_seconds() == 9000
