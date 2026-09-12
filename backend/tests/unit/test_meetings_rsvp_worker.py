"""Unit-тесты cron-обёрток RSVP-воркера: поллер, дайджесты, локи, гейты.

БД/IMAP мокаются — здесь проверяется каркас (гейты, interval-guard, lock,
окно дайджеста, публикация после commit), а не бизнес-логика (она в
integration/test_meetings_rsvp_ingest.py и test_meetings_rsvp_unit.py).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


class _MemRedis:
    """Минимальный redis-двойник: get/set/setnx/eval для локов и interval-guard."""

    def __init__(self, stored: dict[str, str] | None = None) -> None:
        self.stored = dict(stored or {})
        self.set_calls: list[tuple] = []

    async def get(self, key: str) -> str | None:
        return self.stored.get(key)

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        self.set_calls.append((key, value, nx))
        if nx and key in self.stored:
            return False
        self.stored[key] = value
        return True

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        if self.stored.get(key) == token:
            del self.stored[key]
            return 1
        return 0


def _session_ctx() -> AsyncMock:
    """AsyncSessionLocal-двойник: сессия с рабочим async-with db.begin()."""
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.begin = MagicMock(return_value=begin_cm)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


def _mods(enabled: bool = True, rsvp: bool = True) -> object:
    return SimpleNamespace(meetings=SimpleNamespace(enabled=enabled, rsvp_ingest_enabled=rsvp))


class TestPollMeetingsRsvp:
    async def test_no_redis_skipped(self):
        from app.worker.tasks.meetings.rsvp_poll import poll_meetings_rsvp

        assert await poll_meetings_rsvp({}) == {"skipped": "no_redis"}

    async def test_gates_closed_skipped(self):
        from app.worker.tasks.meetings.rsvp_poll import poll_meetings_rsvp

        with patch("app.core.modules_config.load_modules", return_value=_mods(rsvp=False)):
            result = await poll_meetings_rsvp({"redis": _MemRedis()})
        assert result == {"skipped": "rsvp_ingest_disabled"}

    async def test_imap_not_configured_skipped(self):
        from app.worker.tasks.meetings import rsvp_poll
        from app.worker.tasks.meetings.rsvp_poll import poll_meetings_rsvp

        with (
            patch("app.core.modules_config.load_modules", return_value=_mods()),
            patch.object(rsvp_poll, "load_email_settings", return_value=SimpleNamespace()),
            patch.object(rsvp_poll, "imap_configured", return_value=False),
        ):
            result = await poll_meetings_rsvp({"redis": _MemRedis()})
        assert result == {"skipped": "imap_not_configured"}

    async def test_interval_not_elapsed_skipped(self):
        from datetime import UTC, datetime

        from app.worker.tasks.meetings import rsvp_poll
        from app.worker.tasks.meetings.rsvp_poll import poll_meetings_rsvp

        redis = _MemRedis({rsvp_poll.RSVP_LAST_POLL_KEY: datetime.now(UTC).isoformat()})
        with (
            patch("app.core.modules_config.load_modules", return_value=_mods()),
            patch.object(rsvp_poll, "load_email_settings", return_value=SimpleNamespace()),
            patch.object(rsvp_poll, "imap_configured", return_value=True),
        ):
            result = await poll_meetings_rsvp({"redis": redis})
        assert result == {"skipped": "interval_not_elapsed"}

    async def test_lock_held_skipped(self):
        from datetime import UTC, datetime, timedelta

        from app.worker.tasks.meetings import rsvp_poll
        from app.worker.tasks.meetings.rsvp_poll import poll_meetings_rsvp

        stale = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        redis = _MemRedis(
            {
                rsvp_poll.RSVP_LAST_POLL_KEY: stale,
                rsvp_poll.RSVP_POLL_LOCK_KEY: "other-worker-token",
            }
        )
        with (
            patch("app.core.modules_config.load_modules", return_value=_mods()),
            patch.object(rsvp_poll, "load_email_settings", return_value=SimpleNamespace()),
            patch.object(rsvp_poll, "imap_configured", return_value=True),
        ):
            result = await poll_meetings_rsvp({"redis": redis})
        assert result == {"skipped": "lock_held"}

    async def test_no_candidates_short_circuit(self):
        from app.worker.tasks.meetings import rsvp_poll
        from app.worker.tasks.meetings.rsvp_poll import poll_meetings_rsvp

        redis = _MemRedis()
        settings = SimpleNamespace()
        with (
            patch("app.core.modules_config.load_modules", return_value=_mods()),
            patch.object(rsvp_poll, "load_email_settings", return_value=settings),
            patch.object(rsvp_poll, "imap_configured", return_value=True),
            patch.object(rsvp_poll, "fetch_reply_candidates", AsyncMock(return_value=[])),
        ):
            result = await poll_meetings_rsvp({"redis": redis})
        assert result == {"processed": 0}
        assert redis.stored[rsvp_poll.RSVP_LAST_POLL_KEY]  # interval marker written

    async def test_full_cycle_processes_publishes_deletes(self):
        """Один кандидат: ingest → publish → SSE → удаление письма из ящика."""
        from app.services.meetings.rsvp_ingest import RsvpChange
        from app.worker.tasks.meetings import rsvp_poll
        from app.worker.tasks.meetings.rsvp_poll import poll_meetings_rsvp

        change = RsvpChange(
            booking_id=MagicMock(),
            creator_id=MagicMock(),
            booking_title="T",
            date_str="2026-08-20",
            room_ids=[],
            participant_name="Ivan",
            status="accepted",
        )
        outcome = SimpleNamespace(status="applied", changes=[change])
        candidate = SimpleNamespace(uid="7", parsed=MagicMock(), raw=b"x")
        candidate.message_id = "<m@x>"

        publish_mock = AsyncMock()
        redis = _MemRedis()
        settings = SimpleNamespace()
        with (
            patch("app.core.modules_config.load_modules", return_value=_mods()),
            patch.object(rsvp_poll, "load_email_settings", return_value=settings),
            patch.object(rsvp_poll, "imap_configured", return_value=True),
            patch.object(rsvp_poll, "fetch_reply_candidates", AsyncMock(return_value=[candidate])),
            patch.object(rsvp_poll, "AsyncSessionLocal", return_value=_session_ctx()),
            patch.object(rsvp_poll, "apply_reply", AsyncMock(return_value=outcome)),
            patch.object(rsvp_poll, "create_notification", AsyncMock(return_value=publish_mock)),
            patch.object(rsvp_poll, "publish_meeting_event", AsyncMock()) as sse_mock,
            patch.object(rsvp_poll, "delete_reply_messages", AsyncMock(return_value=1)) as del_mock,
        ):
            result = await poll_meetings_rsvp({"redis": redis})

        assert result["processed"] == 1
        assert result["applied"] == 1
        assert result["deleted"] == 1
        del_mock.assert_awaited_once_with(settings, ["7"])
        sse_mock.assert_awaited_once()
        publish_mock.assert_awaited_once()

    async def test_exception_returns_error_and_releases_lock(self):
        from app.worker.tasks.meetings import rsvp_poll
        from app.worker.tasks.meetings.rsvp_poll import poll_meetings_rsvp

        redis = _MemRedis()
        with (
            patch("app.core.modules_config.load_modules", return_value=_mods()),
            patch.object(rsvp_poll, "load_email_settings", return_value=SimpleNamespace()),
            patch.object(rsvp_poll, "imap_configured", return_value=True),
            patch.object(
                rsvp_poll,
                "fetch_reply_candidates",
                AsyncMock(side_effect=RuntimeError("imap down")),
            ),
        ):
            result = await poll_meetings_rsvp({"redis": redis})
        assert result == {"error": "RuntimeError"}
        assert rsvp_poll.RSVP_POLL_LOCK_KEY not in redis.stored  # lock released


class TestRsvpDigestCron:
    async def test_digest_no_redis_skipped(self):
        from app.worker.tasks.meetings.rsvp_digest import send_rsvp_digest

        assert await send_rsvp_digest({}) == {"skipped": "no_redis"}

    async def test_digest_gates_closed_skipped(self):
        from app.worker.tasks.meetings.rsvp_digest import send_rsvp_digest

        with patch("app.core.modules_config.load_modules", return_value=_mods(rsvp=False)):
            assert await send_rsvp_digest({"redis": _MemRedis()}) == {
                "skipped": "rsvp_ingest_disabled"
            }

    async def test_digest_reads_window_and_moves_marker(self):
        from datetime import UTC, datetime, timedelta

        from app.worker.tasks.meetings import rsvp_digest
        from app.worker.tasks.meetings.rsvp_digest import send_rsvp_digest

        old = (datetime.now(UTC) - timedelta(minutes=25)).isoformat()
        redis = _MemRedis({rsvp_digest.DIGEST_LAST_RUN_KEY: old})
        with (
            patch("app.core.modules_config.load_modules", return_value=_mods()),
            patch.object(rsvp_digest, "AsyncSessionLocal", return_value=_session_ctx()),
            patch.object(
                rsvp_digest, "collect_digest_emails", AsyncMock(return_value=3)
            ) as collect_mock,
        ):
            result = await send_rsvp_digest({"redis": redis})

        assert result == {"sent": 3}
        # Окно передано из Redis-ключа, маркер двигается после commit.
        window_start = collect_mock.call_args.kwargs["window_start"]
        age_seconds = (datetime.now(UTC) - window_start).total_seconds()
        assert 24 * 60 < age_seconds < 26 * 60
        assert redis.stored[rsvp_digest.DIGEST_LAST_RUN_KEY] != old

    async def test_final_digest_gates_closed_skipped(self):
        from app.worker.tasks.meetings.rsvp_digest import send_rsvp_final_digest

        with patch("app.core.modules_config.load_modules", return_value=_mods(enabled=False)):
            assert await send_rsvp_final_digest({}) == {"skipped": "module_disabled"}

    async def test_final_digest_calls_process_window(self):
        from app.worker.tasks.meetings.rsvp_digest import send_rsvp_final_digest

        with (
            patch(
                "app.worker.tasks.meetings.rsvp_digest.AsyncSessionLocal",
                return_value=_session_ctx(),
            ),
            patch("app.worker.tasks.meetings.rsvp_digest._gates_open", return_value=None),
            patch(
                "app.worker.tasks.meetings.rsvp_digest.process_final_window",
                AsyncMock(return_value=2),
            ),
        ):
            result = await send_rsvp_final_digest({})
        assert result == {"sent": 2}


# TestDigestHelpers (sync: _participant_name/_wrap_html/_STATUS_LABELS_RU)
# вынесен в test_meetings_rsvp_digest_helpers.py: здесь модульный
# pytestmark = pytest.mark.asyncio, синхронные тесты под ним генерировали
# pytest-asyncio warnings (аудит тестирования 2026-08-23, P3).
