"""Unit + property-based тесты для ``app.services.meetings.bookings_service._helpers``.

Покрывают ранее нетестируемые ветки:
- ``_compute_diff`` — property-тесты через Hypothesis (инварианты алгоритма
  для произвольных множеств пользователей: симметрия, conservation, idempotency).
- ``_to_utc`` / ``_date_range`` — детерминированные edge-cases (naive/aware
  datetime, границы дня в произвольном tz).

Property-тесты (Hypothesis) — главный фокус: ``_compute_diff`` реализует
разность множеств invited-users, и его корректность легче доказать через
инварианты для случайных входов, чем через enumerate-кейсы.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers: _to_utc, _date_range
# ─────────────────────────────────────────────────────────────────────────────


def test_to_utc_keeps_aware_datetime_unchanged_in_utc():
    """Aware datetime в UTC → возвращается как есть (astimezone(UTC) — no-op)."""
    from app.services.meetings.bookings_service._helpers import _to_utc

    dt = datetime(2030, 6, 15, 12, 0, tzinfo=UTC)
    assert _to_utc(dt) == dt
    assert _to_utc(dt).tzinfo is UTC


def test_to_utc_converts_non_utc_aware_to_utc():
    """Aware datetime в другом tz → конвертируется в UTC (значение времени сдвигается)."""
    from app.services.meetings.bookings_service._helpers import _to_utc

    # Москва UTC+3 (фиксированное смещение, без DST)
    moscow_tz = timezone(timedelta(hours=3))
    dt_moscow = datetime(2030, 6, 15, 15, 0, tzinfo=moscow_tz)  # 15:00 MSK
    dt_utc = _to_utc(dt_moscow)
    assert dt_utc.tzinfo is not None
    # 15:00 MSK = 12:00 UTC
    assert dt_utc.hour == 12
    assert dt_utc.utcoffset() == timedelta(0)


def test_to_utc_assigns_utc_to_naive_datetime():
    """Naive datetime (tzinfo=None) → получает tzinfo=UTC без сдвига значений."""
    from app.services.meetings.bookings_service._helpers import _to_utc

    naive = datetime(2030, 6, 15, 12, 0)
    result = _to_utc(naive)
    assert result.tzinfo is UTC
    # Значения времени не меняются (replace, не astimezone)
    assert result.hour == 12
    assert result.year == 2030


def test_date_range_returns_full_day_bounds_in_utc():
    """Для заданной даты возвращает [00:00:00, 23:59:59.999999] UTC."""
    from app.services.meetings.bookings_service._helpers import _date_range

    start, end = _date_range(date(2030, 6, 15), tz_name="UTC")
    assert start.tzinfo is not None
    assert end.tzinfo is not None
    assert start.hour == 0 and start.minute == 0 and start.second == 0
    assert end.hour == 23 and end.minute == 59 and end.second == 59
    assert end.microsecond == 999999
    # start и end — один и тот же день
    assert start.date() == end.date()
    assert start < end


def test_date_range_converts_non_utc_timezone_to_utc():
    """Дата в tz с positive offset → UTC-границы сдвигаются на предыдущий/текущий день."""
    from app.services.meetings.bookings_service._helpers import _date_range

    # Москва (UTC+3, без DST через Europe/Moscow в IANA — но фиксировано +3)
    start, _end = _date_range(date(2030, 6, 15), tz_name="Europe/Moscow")
    # 00:00 MSK = 21:00 UTC предыдущего дня
    assert start.tzinfo is not None
    assert start.utcoffset() == UTC.utcoffset(None)
    # start в UTC — 21:00 14 июня (MSK 00:00 15 июня минус 3 часа)
    assert start.hour == 21
    assert start.day == 14


def test_date_range_handles_dst_timezone():
    """tz с DST (Europe/Berlin) не падает и возвращает валидный 24h-диапазон."""
    from app.services.meetings.bookings_service._helpers import _date_range

    # Зимняя дата (CET = UTC+1)
    start_winter, end_winter = _date_range(date(2030, 1, 15), tz_name="Europe/Berlin")
    # Летняя дата (CEST = UTC+2)
    start_summer, end_summer = _date_range(date(2030, 7, 15), tz_name="Europe/Berlin")
    # Оба валидны и в UTC
    assert start_winter.tzinfo is not None
    assert start_summer.tzinfo is not None
    # 24h-интервал (с учётом микросекунд почти ровно 24h)
    winter_span = end_winter - start_winter
    summer_span = end_summer - start_summer
    assert abs(winter_span.total_seconds() - 24 * 3600) < 1
    assert abs(summer_span.total_seconds() - 24 * 3600) < 1


# ─────────────────────────────────────────────────────────────────────────────
# Property-based tests: _compute_diff invariants (Hypothesis)
# ─────────────────────────────────────────────────────────────────────────────
#
# Стратегия: генерируем две произвольные выборки user_ids (old и new),
# строим из них dict-записи и InvitedUser-объекты, вызываем _compute_diff и
# проверяем алгебраические инварианты множеств:
#   1. Conservation: |added ∪ removed ∪ unchanged| == |symmetric domain|
#   2. Disjoint: added, removed, unchanged попарно не пересекаются
#   3. Reflexive: diff(A, A) → все unchanged, added=removed=∅
#   4. Symmetric: removed(diff(A,B)) == added(diff(B,A)) по user_id (с поправкой
#      на направление: A→B добавил = B→A удалил)
#   5. non_participant_changed пробрасывается как есть
# ─────────────────────────────────────────────────────────────────────────────


# user_id — короткие строки без коллизий с генератором (фиксированный алфавит).
_user_id_strategy = st.text(
    alphabet=st.characters(min_codepoint=48, max_codepoint=122), min_size=1, max_size=8
)
_email_strategy = st.builds(
    lambda local: f"{local}@example.com",
    local=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=8
    ),
)


def _make_invited_user(user_id: str, email: str, full_name: str = ""):
    from app.schemas.meetings import InvitedUser

    return InvitedUser(user_id=user_id, full_name=full_name, email=email)


# Стратегия: набор уникальных пользователей (по user_id)
@st.composite
def _user_set(draw, max_size=8):
    n = draw(st.integers(min_value=0, max_value=max_size))
    seen: set[str] = set()
    users = []
    for _ in range(n):
        uid = draw(_user_id_strategy.filter(lambda u: u not in seen))
        seen.add(uid)
        users.append((uid, draw(_email_strategy)))
    return users


@given(old_users=_user_set(), new_users=_user_set())
@settings(
    max_examples=80, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_compute_diff_conservation_and_disjoint(old_users, new_users):
    """Инвариант 1+2: разбиение полное и попарно непересекающееся.

    Для любых двух множеств A (old) и B (new): каждая запись из A∪B попадает
    ровно в одну из категорий added/removed/unchanged, без дубликатов.
    """
    from app.services.meetings.bookings_service import _compute_diff

    old_dicts = [{"user_id": uid, "email": em, "full_name": ""} for uid, em in old_users]
    new_objs = [_make_invited_user(uid, em) for uid, em in new_users]

    diff = _compute_diff(old_dicts, new_objs, non_participant_changed=False)

    added_ids = {u.user_id for u in diff.added_users}
    removed_ids = {u.user_id for u in diff.removed_users}
    unchanged_ids = {u.user_id for u in diff.unchanged_users}

    old_ids = {uid for uid, _ in old_users}
    new_ids = {uid for uid, _ in new_users}
    union_ids = old_ids | new_ids

    # Инвариант 1: conservation — все id из union покрыты
    assert added_ids | removed_ids | unchanged_ids == union_ids
    # Инвариант 2: disjoint — нет пересечений между категориями
    assert not (added_ids & removed_ids)
    assert not (added_ids & unchanged_ids)
    assert not (removed_ids & unchanged_ids)

    # Точная семантика категорий
    assert added_ids == new_ids - old_ids
    assert removed_ids == old_ids - new_ids
    assert unchanged_ids == old_ids & new_ids


@given(users=_user_set(max_size=10))
@settings(max_examples=50, deadline=None)
def test_compute_diff_reflexive_all_unchanged(users):
    """Инвариант 3: diff(A, A) → все unchanged, added=removed=∅.

    Если старый и новый списки идентичны (по user_id), никто не добавился и не
    удалился. Это базовое свойство тождества множеств.
    """
    from app.services.meetings.bookings_service import _compute_diff

    old_dicts = [{"user_id": uid, "email": em, "full_name": ""} for uid, em in users]
    new_objs = [_make_invited_user(uid, em) for uid, em in users]

    diff = _compute_diff(old_dicts, new_objs, non_participant_changed=False)

    assert diff.added_users == []
    assert diff.removed_users == []
    assert {u.user_id for u in diff.unchanged_users} == {uid for uid, _ in users}


@given(old_users=_user_set(max_size=8), new_users=_user_set(max_size=8))
@settings(max_examples=80, deadline=None)
def test_compute_diff_symmetric_direction_swap(old_users, new_users):
    """Инвариант 4: добавленные в A→B = удалённые в B→A (по user_id).

    Если позвать Алису в новый список (B), то в diff(A→B) она added, а в
    diff(B→A) — removed. Алгоритм должен быть симметричным по направлению.
    """
    from app.services.meetings.bookings_service import _compute_diff

    old_dicts = [{"user_id": uid, "email": em, "full_name": ""} for uid, em in old_users]
    new_objs = [_make_invited_user(uid, em) for uid, em in new_users]

    diff_forward = _compute_diff(old_dicts, new_objs, non_participant_changed=False)
    # Обратное направление: new → old
    new_as_dicts = [{"user_id": uid, "email": em, "full_name": ""} for uid, em in new_users]
    old_as_objs = [_make_invited_user(uid, em) for uid, em in old_users]
    diff_backward = _compute_diff(new_as_dicts, old_as_objs, non_participant_changed=False)

    forward_added = {u.user_id for u in diff_forward.added_users}
    backward_removed = {u.user_id for u in diff_backward.removed_users}
    forward_removed = {u.user_id for u in diff_forward.removed_users}
    backward_added = {u.user_id for u in diff_backward.added_users}

    assert forward_added == backward_removed
    assert forward_removed == backward_added


@given(old_users=_user_set(max_size=5), new_users=_user_set(max_size=5), npc=st.booleans())
@settings(max_examples=40, deadline=None)
def test_compute_diff_non_participant_changed_passthrough(old_users, new_users, npc):
    """Инвариант 5: non_participant_changed пробрасывается в результат как есть."""
    from app.services.meetings.bookings_service import _compute_diff

    old_dicts = [{"user_id": uid, "email": em, "full_name": ""} for uid, em in old_users]
    new_objs = [_make_invited_user(uid, em) for uid, em in new_users]

    diff = _compute_diff(old_dicts, new_objs, non_participant_changed=npc)
    assert diff.non_participant_changed is npc


@given(
    malformed=st.lists(
        st.fixed_dictionaries({}) | st.fixed_dictionaries({"full_name": st.text(max_size=5)}),
        max_size=5,
    )
)
@settings(max_examples=30, deadline=None)
def test_compute_diff_filters_all_malformed_entries(malformed):
    """Все malformed-записи (без user_id или email) фильтруются, не падая.

    Это расширяет существующие unit-тесты: вместо конкретных 1-2 malformed
    проверяем, что произвольная смесь неполных dict'ов не ломает алгоритм
    и не приводит к KeyError/TypeError.
    """
    from app.services.meetings.bookings_service import _compute_diff

    # Все записи malformed (нет user_id и/или email) → valid_old пустой
    diff = _compute_diff(list(malformed), [], non_participant_changed=False)
    assert diff.removed_users == []
    assert diff.unchanged_users == []
    assert diff.added_users == []
