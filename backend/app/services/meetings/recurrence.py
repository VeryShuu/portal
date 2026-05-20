from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from dateutil import rrule as rrule_lib
from dateutil.rrule import rrule

from app.schemas.meetings import RecurrenceRule


def expand_recurrence(
    start: datetime,
    end: datetime,
    rule: RecurrenceRule,
    tz: str,
) -> list[tuple[datetime, datetime]]:
    duration = end - start

    try:
        local_tz = ZoneInfo(tz)
    except Exception:
        local_tz = UTC
    local_start = start.astimezone(local_tz) if start.tzinfo else start.replace(tzinfo=UTC)

    until_dt = datetime(
        rule.until_date.year,
        rule.until_date.month,
        rule.until_date.day,
        23,
        59,
        59,
        tzinfo=local_tz,
    ).astimezone(UTC)

    weekday_map = {
        0: rrule_lib.MO,
        1: rrule_lib.TU,
        2: rrule_lib.WE,
        3: rrule_lib.TH,
        4: rrule_lib.FR,
        5: rrule_lib.SA,
        6: rrule_lib.SU,
    }
    start_weekday = weekday_map[local_start.weekday()]

    if rule.freq == "DAILY":
        rr = rrule(rrule_lib.DAILY, dtstart=start, until=until_dt)
    elif rule.freq == "WEEKDAYS":
        rr = rrule(
            rrule_lib.WEEKLY,
            dtstart=start,
            until=until_dt,
            byweekday=[rrule_lib.MO, rrule_lib.TU, rrule_lib.WE, rrule_lib.TH, rrule_lib.FR],
        )
    elif rule.freq == "WEEKLY":
        rr = rrule(
            rrule_lib.WEEKLY,
            dtstart=start,
            until=until_dt,
            byweekday=[start_weekday],
        )
    elif rule.freq == "BIWEEKLY":
        rr = rrule(
            rrule_lib.WEEKLY,
            dtstart=start,
            until=until_dt,
            interval=2,
            byweekday=[start_weekday],
        )
    elif rule.freq == "MONTHLY":
        if local_start.day > 28:
            raise ValueError(
                "Monthly recurrence with start day > 28 is not supported. "
                "Choose a start date with day in range 1-28."
            )
        rr = rrule(
            rrule_lib.MONTHLY,
            dtstart=start,
            until=until_dt,
            bymonthday=[local_start.day],
        )
    else:
        raise ValueError(f"Unknown recurrence frequency: {rule.freq}")

    instances = list(rr)

    if len(instances) > 31:
        raise ValueError("Recurrence generates more than 31 instances")

    result: list[tuple[datetime, datetime]] = []
    for dt in instances:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        instance_start = dt.astimezone(UTC)
        instance_end = instance_start + duration
        result.append((instance_start, instance_end))

    return result


def parse_rrule_string(rrule_str: str) -> RecurrenceRule | None:
    """Best-effort reverse of `build_rrule_string`.

    Returns None if FREQ/UNTIL cannot be extracted.
    """
    from datetime import date as _date

    parts: dict[str, str] = {}
    for chunk in (rrule_str or "").split(";"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            parts[k.upper()] = v

    freq = parts.get("FREQ")
    until = parts.get("UNTIL")
    if not freq or not until:
        return None

    try:
        until_date = _date(int(until[0:4]), int(until[4:6]), int(until[6:8]))
    except (ValueError, IndexError):
        return None

    interval = parts.get("INTERVAL")
    byday = parts.get("BYDAY")

    if freq == "DAILY":
        mapped = "DAILY"
    elif freq == "WEEKLY" and byday == "MO,TU,WE,TH,FR":
        mapped = "WEEKDAYS"
    elif freq == "WEEKLY" and interval == "2":
        mapped = "BIWEEKLY"
    elif freq == "WEEKLY":
        mapped = "WEEKLY"
    elif freq == "MONTHLY":
        mapped = "MONTHLY"
    else:
        return None

    return RecurrenceRule(freq=mapped, until_date=until_date)


def build_rrule_string(rule: RecurrenceRule, start: datetime, tz: str = "UTC") -> str:
    try:
        local_tz = ZoneInfo(tz)
    except Exception:
        local_tz = UTC
    local_start = start.astimezone(local_tz) if start.tzinfo else start.replace(tzinfo=UTC)

    weekday_names = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    start_weekday = weekday_names[local_start.weekday()]
    until_str = rule.until_date.strftime("%Y%m%dT235959Z")

    if rule.freq == "DAILY":
        return f"FREQ=DAILY;UNTIL={until_str}"
    elif rule.freq == "WEEKDAYS":
        return f"FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL={until_str}"
    elif rule.freq == "WEEKLY":
        return f"FREQ=WEEKLY;BYDAY={start_weekday};UNTIL={until_str}"
    elif rule.freq == "BIWEEKLY":
        return f"FREQ=WEEKLY;INTERVAL=2;BYDAY={start_weekday};UNTIL={until_str}"
    elif rule.freq == "MONTHLY":
        return f"FREQ=MONTHLY;BYMONTHDAY={local_start.day};UNTIL={until_str}"
    else:
        raise ValueError(f"Unknown recurrence frequency: {rule.freq}")
