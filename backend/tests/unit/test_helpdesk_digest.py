"""Unit-тесты ежедневной email-сводки по helpdesk-заявкам.

Покрытие:
* ``should_send_today`` — расписание (час/минута/будни-daily/enabled).
* ``already_sent_today`` — идемпотентность внутри дня.
* ``build_digest_bodies`` — рендер секций, XSS-экранирование, абсолютная
  ссылка через ``portal_base_url``, плюрализация «дней в работе», пустые блоки.
* ``build_digest_subject`` — фиксированная тема.

DB-зависимые ``collect_*`` (фильтрация по статусам/assignee) — в
``test_helpdesk_digest_collect.py`` (integration, нужен PostgreSQL для
``func.extract``). Здесь — только чистые функции.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.user import User
from app.services.helpdesk.digest import (
    DigestData,
    DigestTicketRow,
    _plural_days,
    already_sent_today,
    build_digest_bodies,
    build_digest_subject,
    should_send_today,
)

BASE_URL = "https://portal.company.local"


def _agent(*, full_name: str = "Иван Иванов", email: str = "agent@portal.local") -> User:
    return User(id=uuid.uuid4(), email=email, full_name=full_name, role="editor")


def _row(
    *,
    number: int = 10,
    subject: str = "Сломался VPN",
    author: str = "Петя Сидоров",
    days: int = 3,
) -> DigestTicketRow:
    return DigestTicketRow(
        ticket_id=uuid.uuid4(),
        number=number,
        subject=subject,
        author_display=author,
        days_in_work=days,
    )


# ---------------------------------------------------------------------------
# should_send_today
# ---------------------------------------------------------------------------


class TestShouldSendToday:
    def test_exact_match_weekday(self) -> None:
        # 2026-07-01 — среда (weekday=2), 08:00 UTC.
        now = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
        assert should_send_today(
            now, enabled=True, digest_hour=8, digest_minute=0, digest_schedule="weekdays"
        )

    def test_wrong_hour(self) -> None:
        now = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
        assert not should_send_today(
            now, enabled=True, digest_hour=8, digest_minute=0, digest_schedule="daily"
        )

    def test_wrong_minute(self) -> None:
        now = datetime(2026, 7, 1, 8, 30, tzinfo=UTC)
        assert not should_send_today(
            now, enabled=True, digest_hour=8, digest_minute=0, digest_schedule="daily"
        )

    def test_disabled(self) -> None:
        now = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
        assert not should_send_today(
            now, enabled=False, digest_hour=8, digest_minute=0, digest_schedule="daily"
        )

    def test_weekday_schedule_skips_saturday(self) -> None:
        # 2026-07-04 — суббота (weekday=5).
        now = datetime(2026, 7, 4, 8, 0, tzinfo=UTC)
        assert not should_send_today(
            now, enabled=True, digest_hour=8, digest_minute=0, digest_schedule="weekdays"
        )

    def test_weekday_schedule_skips_sunday(self) -> None:
        # 2026-07-05 — воскресенье (weekday=6).
        now = datetime(2026, 7, 5, 8, 0, tzinfo=UTC)
        assert not should_send_today(
            now, enabled=True, digest_hour=8, digest_minute=0, digest_schedule="weekdays"
        )

    def test_daily_schedule_sends_on_weekend(self) -> None:
        now = datetime(2026, 7, 4, 8, 0, tzinfo=UTC)  # суббота
        assert should_send_today(
            now, enabled=True, digest_hour=8, digest_minute=0, digest_schedule="daily"
        )

    def test_non_zero_minute(self) -> None:
        now = datetime(2026, 7, 1, 9, 15, tzinfo=UTC)
        assert should_send_today(
            now, enabled=True, digest_hour=9, digest_minute=15, digest_schedule="daily"
        )


# ---------------------------------------------------------------------------
# already_sent_today
# ---------------------------------------------------------------------------


class TestAlreadySentToday:
    def test_none_last_sent(self) -> None:
        assert not already_sent_today(None, now=datetime(2026, 7, 1, 8, 0, tzinfo=UTC))

    def test_same_day(self) -> None:
        now = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
        last = datetime(2026, 7, 1, 8, 0, tzinfo=UTC).isoformat()
        assert already_sent_today(last, now=now)

    def test_different_day(self) -> None:
        now = datetime(2026, 7, 2, 8, 0, tzinfo=UTC)
        last = datetime(2026, 7, 1, 8, 0, tzinfo=UTC).isoformat()
        assert not already_sent_today(last, now=now)

    def test_garbage_last_sent(self) -> None:
        # Битое значение — не считаем «уже отправлено», идём дальше.
        assert not already_sent_today("not-a-date", now=datetime(2026, 7, 1, 8, 0, tzinfo=UTC))


# ---------------------------------------------------------------------------
# build_digest_subject
# ---------------------------------------------------------------------------


class TestDigestSubject:
    def test_fixed_subject(self) -> None:
        assert build_digest_subject() == "Ежедневная сводка заявок техподдержки"

    def test_no_ticket_token(self) -> None:
        # Дайджест — не часть треда тикета, токена [#TKT-N] быть не должно.
        assert "[#TKT-" not in build_digest_subject()


# ---------------------------------------------------------------------------
# _plural_days
# ---------------------------------------------------------------------------


class TestPluralDays:
    def test_one_day(self) -> None:
        assert _plural_days(1) == "1 день"

    def test_two_days(self) -> None:
        assert _plural_days(2) == "2 дня"

    def test_five_days(self) -> None:
        assert _plural_days(5) == "5 дней"

    def test_eleven_days(self) -> None:
        # 11 — исключение («11 дней», не «11 дня»).
        assert _plural_days(11) == "11 дней"

    def test_twenty_one_days(self) -> None:
        # 21 — «21 день» (1 + исключение 11 не срабатывает).
        assert _plural_days(21) == "21 день"

    def test_zero_days(self) -> None:
        assert _plural_days(0) == "0 дней"


# ---------------------------------------------------------------------------
# build_digest_bodies
# ---------------------------------------------------------------------------


class TestDigestBodies:
    def test_both_blocks_present(self) -> None:
        agent = _agent()
        data = DigestData(
            assigned=[_row(number=10, subject="VPN", days=2)],
            unassigned=[_row(number=11, subject="Принтер", days=5)],
        )
        plain, html_body = build_digest_bodies(agent, data, portal_base_url=BASE_URL)

        assert "Ваши заявки в работе" in plain
        assert "Неназначенные заявки" in plain
        assert "#10" in plain and "#11" in plain
        assert "VPN" in plain and "Принтер" in plain
        assert "2 дня" in plain and "5 дней" in plain
        # Абсолютная ссылка.
        ticket_id = data.assigned[0].ticket_id
        assert f"{BASE_URL}/helpdesk/tickets/{ticket_id}" in plain
        assert f"{BASE_URL}/helpdesk/tickets/{ticket_id}" in html_body

    def test_only_assigned_block(self) -> None:
        data = DigestData(assigned=[_row()], unassigned=[])
        plain, _html = build_digest_bodies(_agent(), data, portal_base_url=BASE_URL)
        assert "Ваши заявки в работе" in plain
        assert "Неназначенные заявки" not in plain

    def test_only_unassigned_block(self) -> None:
        data = DigestData(assigned=[], unassigned=[_row()])
        plain, _html = build_digest_bodies(_agent(), data, portal_base_url=BASE_URL)
        assert "Неназначенные заявки" in plain
        assert "Ваши заявки в работе" not in plain

    def test_html_escapes_user_data(self) -> None:
        """XSS-защита: тема/имя со спецсимволами экранируются."""
        data = DigestData(
            assigned=[
                _row(subject="<script>alert(1)</script>", author="<b>Evil</b>")
            ],
            unassigned=[],
        )
        _plain, html_body = build_digest_bodies(_agent(), data, portal_base_url=BASE_URL)
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body
        assert "<b>" not in html_body
        assert "&lt;b&gt;" in html_body

    def test_base_url_trailing_slash_normalized(self) -> None:
        """Trailing-slash в portal_base_url не даёт двойной слэш в ссылке."""
        data = DigestData(assigned=[_row()], unassigned=[])
        _plain, html_body = build_digest_bodies(
            _agent(), data, portal_base_url=f"{BASE_URL}/"
        )
        ticket_id = data.assigned[0].ticket_id
        assert f"{BASE_URL}/helpdesk/tickets/{ticket_id}" in html_body
        assert "//helpdesk" not in html_body

    def test_link_contains_ticket_id(self) -> None:
        data = DigestData(assigned=[_row()], unassigned=[])
        _plain, html_body = build_digest_bodies(_agent(), data, portal_base_url=BASE_URL)
        ticket_id = data.assigned[0].ticket_id
        assert str(ticket_id) in html_body

    def test_greeting_uses_agent_name(self) -> None:
        agent = _agent(full_name="Мария Петрова")
        data = DigestData(assigned=[], unassigned=[])
        plain, html_body = build_digest_bodies(agent, data, portal_base_url=BASE_URL)
        assert "Мария Петрова" in plain
        assert "Мария Петрова" in html_body

    def test_greeting_falls_back_to_email(self) -> None:
        agent = _agent(full_name="", email="x@portal.local")
        data = DigestData(assigned=[], unassigned=[])
        plain, _html = build_digest_bodies(agent, data, portal_base_url=BASE_URL)
        assert "x@portal.local" in plain


class TestDigestDataEmpty:
    def test_is_empty_when_both_empty(self) -> None:
        assert DigestData(assigned=[], unassigned=[]).is_empty()

    def test_not_empty_when_assigned(self) -> None:
        assert not DigestData(assigned=[_row()], unassigned=[]).is_empty()

    def test_not_empty_when_unassigned(self) -> None:
        assert not DigestData(assigned=[], unassigned=[_row()]).is_empty()
