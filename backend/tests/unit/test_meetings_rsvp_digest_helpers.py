"""Sync-хелперы RSVP-дайджестов (participant name / HTML-обёртка / лейблы).

Вынесены из test_meetings_rsvp_worker.py (аудит тестирования 2026-08-23,
P3): в том файле модульный ``pytestmark = pytest.mark.asyncio``, и три
синхронных теста под этим маркером генерировали pytest-asyncio warnings.
Здесь маркера нет — функции чисто синхронные.
"""

from __future__ import annotations

from types import SimpleNamespace


class TestDigestHelpers:
    def test_participant_name_fallback_to_email(self):
        from app.worker.tasks.meetings.rsvp_digest import _participant_name

        booking = SimpleNamespace(
            invited_users=[{"email": "A@X.com", "full_name": "Ann"}, {"email": "b@x.com"}]
        )
        assert _participant_name(booking, "a@x.com") == "Ann"
        assert _participant_name(booking, "stranger@x.com") == "stranger@x.com"

    def test_wrap_html_escapes_title(self):
        from app.worker.tasks.meetings.rsvp_digest import _wrap_html

        html = _wrap_html("<script>", ["<b>safe</b>"])
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<li " in html

    def test_status_labels_complete(self):
        from app.worker.tasks.meetings.rsvp_digest import _STATUS_LABELS_RU, _STATUS_VERBS_RU

        for status in ("accepted", "declined", "tentative"):
            assert status in _STATUS_LABELS_RU
            assert status in _STATUS_VERBS_RU

    def test_local_start_str_converts_utc_to_portal_tz(self):
        from datetime import UTC, datetime

        from app.worker.tasks.meetings.rsvp_digest import _local_start_str

        # 06:30 UTC = 09:30 МСК: до фикса strftime показывал бы 06:30.
        start = datetime(2026, 9, 1, 6, 30, tzinfo=UTC)
        assert _local_start_str(start, "Europe/Moscow", "%d.%m %H:%M") == "01.09 09:30"

    def test_local_start_str_date_rolls_over_near_midnight(self):
        from datetime import UTC, datetime

        from app.worker.tasks.meetings.rsvp_digest import _local_start_str

        # 21:30 UTC 31 августа = 00:30 1 сентября МСК — локализация меняет дату.
        start = datetime(2026, 8, 31, 21, 30, tzinfo=UTC)
        assert _local_start_str(start, "Europe/Moscow", "%d.%m %H:%M") == "01.09 00:30"

    def test_local_start_str_naive_treated_as_utc(self):
        from datetime import datetime

        from app.worker.tasks.meetings.rsvp_digest import _local_start_str

        start = datetime(2026, 9, 1, 6, 30)  # naive — как записи без tz
        assert _local_start_str(start, "Europe/Moscow", "%H:%M") == "09:30"
