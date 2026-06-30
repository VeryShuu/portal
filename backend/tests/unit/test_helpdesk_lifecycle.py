"""Unit-тесты статус-машины helpdesk (Этап 3) — чистая логика без БД.

Покрывают переходы из ТЗ §4.2.1: agent-set, requester-reply (reopen
pending/resolved), closed-reopen-window, agent outbound reply.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.constants import HELPDESK_REOPEN_WINDOW_DAYS
from app.services.helpdesk.lifecycle import (
    AGENT_SETTABLE_STATUSES,
    IllegalTransitionError,
    agent_outbound_reply,
    agent_set_status,
    closed_reopen_eligible,
    requester_reply,
    requester_reply_on_closed,
)


class TestAgentSetStatus:
    @pytest.mark.parametrize("current", ["open", "pending", "resolved", "closed"])
    def test_idempotent_same_status(self, current: str) -> None:
        # Переход в текущий (agent-settable) статус — no-op.
        # ``new`` сюда не входит: PATCH /status с target=new запрещён всегда
        # (``new`` — стартовое состояние, его нельзя выставить вручную).
        result = agent_set_status(current, current)
        assert result.status == current
        assert not result.set_closed

    def test_to_open(self) -> None:
        assert agent_set_status("new", "open").status == "open"

    def test_to_pending(self) -> None:
        assert agent_set_status("open", "pending").status == "pending"

    def test_to_resolved(self) -> None:
        assert agent_set_status("open", "resolved").status == "resolved"

    def test_to_closed_sets_closed_flag(self) -> None:
        result = agent_set_status("resolved", "closed")
        assert result.status == "closed"
        assert result.set_closed

    def test_admin_force_close_from_open(self) -> None:
        # Принудительное закрытие админом из любого активного статуса.
        assert agent_set_status("open", "closed").set_closed

    def test_new_to_closed_allowed(self) -> None:
        # Краевой случай: админ может сразу закрыть спам.
        assert agent_set_status("new", "closed").set_closed

    @pytest.mark.parametrize("target", ["new", "archived", "", "OPEN", "deleted"])
    def test_invalid_target_raises(self, target: str) -> None:
        with pytest.raises(IllegalTransitionError) as exc:
            agent_set_status("open", target)
        assert exc.value.current == "open"
        # ``new`` и ``archived`` не входят в agent-settable набор.
        assert set(exc.value.allowed) == AGENT_SETTABLE_STATUSES


class TestRequesterReply:
    @pytest.mark.parametrize("current", ["pending", "resolved"])
    def test_reopens_to_open(self, current: str) -> None:
        assert requester_reply(current).status == "open"

    @pytest.mark.parametrize("current", ["new", "open"])
    def test_keeps_status(self, current: str) -> None:
        assert requester_reply(current).status == current


class TestClosedReopenWindow:
    def test_eligible_within_window(self) -> None:
        now = datetime.now(UTC)
        closed_at = now - timedelta(days=1)
        assert closed_reopen_eligible(closed_at, now=now) is True

    def test_not_eligible_after_window(self) -> None:
        now = datetime.now(UTC)
        closed_at = now - timedelta(days=HELPDESK_REOPEN_WINDOW_DAYS + 1)
        assert closed_reopen_eligible(closed_at, now=now) is False

    def test_boundary_inclusive(self) -> None:
        # Ровно в окне — ещё можно.
        now = datetime.now(UTC)
        closed_at = now - timedelta(days=HELPDESK_REOPEN_WINDOW_DAYS)
        assert closed_reopen_eligible(closed_at, now=now) is True

    def test_no_closed_at_not_eligible(self) -> None:
        # Безопасный дефолт — не реопенить вслепую.
        assert closed_reopen_eligible(None) is False

    def test_reply_reopens_in_window(self) -> None:
        now = datetime.now(UTC)
        closed_at = now - timedelta(days=1)
        result = requester_reply_on_closed(closed_at, now=now)
        assert result.status == "open"
        assert result.cleared_closed

    def test_reply_noop_after_window(self) -> None:
        now = datetime.now(UTC)
        closed_at = now - timedelta(days=HELPDESK_REOPEN_WINDOW_DAYS + 5)
        result = requester_reply_on_closed(closed_at, now=now)
        assert result.status == "closed"
        assert not result.cleared_closed


class TestAgentOutboundReply:
    @pytest.mark.parametrize("current", ["new", "open", "pending"])
    def test_public_reply_sets_pending(self, current: str) -> None:
        # Публичный ответ агента → ждём клиента.
        assert agent_outbound_reply(current).status == "pending"
