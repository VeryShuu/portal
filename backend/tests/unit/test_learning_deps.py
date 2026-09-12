"""Unit-тесты принципа learner (app.api.deps.get_current_learner).

Покрывает контракт §10.2 ТЗ: типизированный принципал по cookie
``learning_session``, 401 во всех отказных ветках. Ограниченные сессии
(restricted_to) упразднены вместе с паролями (миграция 113): резолвер
игнорирует лишние поля старых payload'ов.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.deps import get_current_learner
from app.services.learning.sessions import SESSION_KEY_PREFIX, build_login_payload
from tests.unit.test_learning_sessions import FakeRedis

_ACCOUNT_ID = str(uuid.uuid4())
_NOW = datetime.now(UTC)


def _account() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.UUID(_ACCOUNT_ID),
        email=" learner@example.com ".strip(),
        status="active",
        deleted_at=None,
    )


def _request(sid: str | None) -> tuple[SimpleNamespace, str | None]:
    req = SimpleNamespace(cookies={}, state=SimpleNamespace())
    if sid:
        req.cookies["learning_session"] = sid
    return req, sid


class TestGetCurrentLearner:
    @pytest.mark.asyncio
    async def test_no_cookie_401(self):
        req, _ = _request(None)
        redis = FakeRedis()
        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await get_current_learner(req, redis, db, session_id=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_session_401(self):
        req, sid = _request("missing")
        with pytest.raises(HTTPException) as exc:
            await get_current_learner(req, FakeRedis(), MagicMock(), session_id=sid)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_non_learning_principal_401(self):
        r = FakeRedis()
        payload = {"principal_type": "portal_user", "account_id": _ACCOUNT_ID}
        await r.setex(f"{SESSION_KEY_PREFIX}s", 60, json.dumps(payload))
        req, sid = _request("s")
        with pytest.raises(HTTPException) as exc:
            await get_current_learner(req, r, MagicMock(), session_id=sid)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_active_account_returns_principal(self):
        r = FakeRedis()
        await r.setex(
            f"{SESSION_KEY_PREFIX}s",
            60,
            json.dumps(build_login_payload(_ACCOUNT_ID)),
        )
        account_row = _account()
        db = MagicMock()
        db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: account_row))
        req, sid = _request("s")
        out = await get_current_learner(req, r, db, session_id=sid)
        assert out.id == account_row.id

    @pytest.mark.asyncio
    async def test_legacy_payload_with_restricted_field_still_resolves(self):
        # Сессии, созданные до passwordless (миграция 113), содержали
        # restricted_to; лишнее поле резолвер игнорирует — 8-часовая сессия
        # не должна отвалиться на релизе.
        r = FakeRedis()
        payload = build_login_payload(_ACCOUNT_ID)
        payload["restricted_to"] = "change_password"
        await r.setex(f"{SESSION_KEY_PREFIX}s", 60, json.dumps(payload))
        db = MagicMock()
        db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: _account()))
        req, sid = _request("s")
        out = await get_current_learner(req, r, db, session_id=sid)
        assert out.id == _account().id

    @pytest.mark.asyncio
    async def test_deleted_or_blocked_account_401(self):
        r = FakeRedis()
        await r.setex(
            f"{SESSION_KEY_PREFIX}s",
            60,
            json.dumps(build_login_payload(_ACCOUNT_ID)),
        )
        db = MagicMock()
        # Фильтр deleted_at IS NULL AND status='active' живёт в SQL; учётка не
        # active → строка не проходит выборку, резолвер получает None и отвечает 401.
        db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
        req, sid = _request("s")
        with pytest.raises(HTTPException) as exc:
            await get_current_learner(req, r, db, session_id=sid)
        assert exc.value.status_code == 401


class TestLearningGatesExtra:
    @pytest.mark.asyncio
    async def test_learning_admin_gate_member_passes(self):
        from app.api.deps import require_learning_admin

        user = SimpleNamespace(id="u2", role="editor")
        db = MagicMock()
        db.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: object()))
        assert await require_learning_admin(user, db) is user

    @pytest.mark.asyncio
    async def test_learner_invalid_account_uuid_401(self):
        r = FakeRedis()
        payload = build_login_payload(_ACCOUNT_ID)
        payload["account_id"] = "not-a-uuid"
        await r.setex(f"{SESSION_KEY_PREFIX}s", 60, json.dumps(payload))
        req, sid = _request("s")
        with pytest.raises(HTTPException) as exc:
            await get_current_learner(req, r, MagicMock(), session_id=sid)
        assert exc.value.status_code == 401
