"""Unit-тесты: сессии learner, изоляция пространств ключей, гейты deps.

Контракт §10.2 ТЗ: learner-сессия живёт в ``learning_session:*`` и не
пересекается с портал-сессиями ``session:*``; портальный резолвер её не видит.
Redis заменяется in-memory двойником (setex/get/delete/sadd/srem/smembers/expire).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from app.services.learning import sessions as ls


class FakeRedis:
    """Минимальный async-двойник Redis для тех операций, что использует сервис."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.sets: dict[str, set[str]] = {}
        self.expires: dict[str, int] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
            if k in self.sets:
                del self.sets[k]
                n += 1
        return n

    async def sadd(self, key: str, member: str) -> int:
        s = self.sets.setdefault(key, set())
        before = len(s)
        s.add(member)
        return len(s) - before

    async def srem(self, key: str, *members: str) -> int:
        s = self.sets.get(key)
        if not s:
            return 0
        before = len(s)
        s.difference_update(members)
        return before - len(s)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return key in self.store or key in self.sets


def _redis() -> FakeRedis:
    return FakeRedis()


# ── пространство ключей ──────────────────────────────────────────────────────


class TestSessionKeyIsolation:
    @pytest.mark.asyncio
    async def test_keys_use_learning_prefix(self):
        r = _redis()
        await ls.save_session(r, "sid1", "acc1", {"account_id": "acc1"})
        assert f"{ls.SESSION_KEY_PREFIX}sid1" in r.store
        assert f"{ls._SESSIONS_INDEX_PREFIX}acc1" in r.sets

    @pytest.mark.asyncio
    async def test_portal_session_key_untouched_by_learning_delete(self):
        """learner-delete трогает только learning_*: портальная сессия выживает."""
        r = _redis()
        portal_key = "session:portal_sid"
        r.store[portal_key] = "{}"
        await ls.save_session(r, "learner_sid", "acc1", {"account_id": "acc1"})
        await ls.delete_session(r, "learner_sid")
        assert portal_key in r.store  # контраст — вот это не должно было умереть
        assert f"{ls.SESSION_KEY_PREFIX}learner_sid" not in r.store

    def test_cookie_name_differs_from_portal(self):
        from app.core.security import SESSION_COOKIE_NAME

        assert ls.COOKIE_NAME != SESSION_COOKIE_NAME

    def test_login_payload_typed_principal(self):
        # Passwordless (миграция 113): payload без restricted-полей; старые
        # сессии с лишним restricted_to резолвер игнорирует (см. test_learning_deps).
        payload = ls.build_login_payload("acc")
        assert payload == {
            "principal_type": "learning_account",
            "account_id": "acc",
        }


# ── жизненный цикл ───────────────────────────────────────────────────────────


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_save_get_roundtrip_and_sliding_window(self):
        r = _redis()
        await ls.save_session(r, "s", "a", {"account_id": "a"})
        payload = await ls.get_session_payload(r, "s")
        assert payload == {"account_id": "a"}

    @pytest.mark.asyncio
    async def test_get_unknown_returns_none(self):
        assert await ls.get_session_payload(_redis(), "nope") is None

    @pytest.mark.asyncio
    async def test_delete_removes_index_member(self):
        r = _redis()
        await ls.save_session(r, "s", "a", {"account_id": "a"})
        await ls.delete_session(r, "s")
        assert await ls.get_session_payload(r, "s") is None
        assert "s" not in await r.smembers(f"{ls._SESSIONS_INDEX_PREFIX}a")

    @pytest.mark.asyncio
    async def test_invalidate_all_clears_every_device(self):
        r = _redis()
        await ls.save_session(r, "s1", "a", {"account_id": "a"})
        await ls.save_session(r, "s2", "a", {"account_id": "a"})
        n = await ls.invalidate_all_sessions(r, "a")
        assert n == 2
        assert await ls.get_session_payload(r, "s1") is None
        assert await ls.get_session_payload(r, "s2") is None
        assert not await r.smembers(f"{ls._SESSIONS_INDEX_PREFIX}a")

    @pytest.mark.asyncio
    async def test_sliding_access_extends_index_ttl(self):
        """Ревью 2026-08-28: sliding продлевает и индекс учётки, иначе через
        9ч invalidate_all_sessions не находит живую сессию."""
        r = _redis()
        await ls.save_session(r, "s", "a", {"account_id": "a"})
        await ls.get_session_payload(r, "s")
        assert r.expires[f"{ls._SESSIONS_INDEX_PREFIX}a"] == ls._INDEX_TTL
        assert r.expires[f"{ls.SESSION_KEY_PREFIX}s"] == ls.SESSION_TTL

    @pytest.mark.asyncio
    async def test_sliding_access_restores_expired_index(self):
        """Индекс истёк по TTL (давно логинились), сессия жива: resolve
        восстанавливает индекс — «выйти со всех устройств» снова работает."""
        r = _redis()
        await ls.save_session(r, "s", "a", {"account_id": "a"})
        r.sets.pop(f"{ls._SESSIONS_INDEX_PREFIX}a")  # имитация истёкшего TTL
        payload = await ls.get_session_payload(r, "s")
        assert payload == {"account_id": "a"}
        assert "s" in await r.smembers(f"{ls._SESSIONS_INDEX_PREFIX}a")
        assert await ls.invalidate_all_sessions(r, "a") == 1

    @pytest.mark.asyncio
    async def test_corrupt_payload_deleted_silently(self):
        r = _redis()
        r.store[f"{ls.SESSION_KEY_PREFIX}bad"] = "{not-json"
        await ls.delete_session(r, "bad")
        assert f"{ls.SESSION_KEY_PREFIX}bad" not in r.store


# ── гейты deps ───────────────────────────────────────────────────────────────


class TestLearningGates:
    @pytest.mark.asyncio
    async def test_learning_admin_gate_admin_role_passes_without_db_hit(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from app.api.deps import require_learning_admin

        admin = SimpleNamespace(id="u1", role="admin")
        db = MagicMock()
        assert await require_learning_admin(admin, db) is admin
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_learning_admin_gate_non_member_403(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from app.api.deps import require_learning_admin

        user = SimpleNamespace(id="u2", role="reader")
        db = MagicMock()
        db.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: None))
        with pytest.raises(HTTPException) as exc:
            await require_learning_admin(user, db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_module_gate_disabled_returns_404(self, monkeypatch: pytest.MonkeyPatch):
        from types import SimpleNamespace

        from app.api.deps import require_learning_module
        from app.core import modules_config

        async def fake_load(redis):
            return SimpleNamespace(learning=SimpleNamespace(enabled=False))

        # deps импортирует load_modules_shared внутри функции — патчим источник.
        monkeypatch.setattr(modules_config, "load_modules_shared", fake_load)

        with pytest.raises(HTTPException) as exc:
            await require_learning_module(None)  # type: ignore[arg-type]
        assert exc.value.status_code == 404

    def test_auth_routes_gated_by_module(self):
        """Ревью 2026-08-28: login/forgot/reset не живут при выключенном модуле —
        на auth-роутере висит require_learning_module, как у остальных контуров."""
        from app.api.learning import auth_routes

        deps = [getattr(d, "dependency", None) for d in auth_routes.router.dependencies]
        assert any(getattr(d, "__name__", "") == "require_learning_module" for d in deps)
