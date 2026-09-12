"""Unit-тесты для `app/core/bootstrap.py::bootstrap_admin`.

Покрытие основных ветвей:
- ранний выход без admin_email / admin_password / local_auth_enabled
- xact advisory-lock берётся первым statement'ом (миграция с session-level
  try_lock: unlock после commit попадал на другое соединение пула и лок
  утекал — ревью 2026-08-28)
- существующий пользователь:
  - роль/auth_source синхронизируются, password не трогаем
  - admin_password_reset_on_start=True → password обновлён
  - password_hash пустой → password выставляется
- нет такого пользователя, но есть другой admin → не создаём
- нет ни такого пользователя, ни другого admin → INSERT
- pg_advisory_unlock нигде не выполняется (лок освобождает сам COMMIT)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.bootstrap import bootstrap_admin


def _make_settings(
    *,
    admin_email: str | None = "admin@example.com",
    admin_password: str | None = "secret-pw-12345",
    local_auth_enabled: bool = True,
    admin_password_reset_on_start: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        admin_email=admin_email,
        admin_password=admin_password,
        local_auth_enabled=local_auth_enabled,
        admin_password_reset_on_start=admin_password_reset_on_start,
    )


class _ScalarResult:
    """Минимальный SQLAlchemy-style Result-объект."""

    def __init__(self, scalar: object = None, scalar_one_or_none: object | None = None):
        self._scalar = scalar
        self._son = scalar_one_or_none

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._son


class _FakeSession:
    """Фейк AsyncSession: возвращает заранее заготовленные Results по очереди."""

    def __init__(self, results: list[_ScalarResult]):
        self._results = list(results)
        self.executed: list[tuple] = []
        self.commits = 0

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_a) -> None:
        return None

    async def execute(self, stmt, params=None):
        self.executed.append((stmt, params))
        if not self._results:
            return _ScalarResult()
        return self._results.pop(0)

    async def commit(self) -> None:
        self.commits += 1


def _patch_session(session: _FakeSession):
    """patch context для `AsyncSessionLocal()` → session."""
    return patch("app.core.bootstrap.AsyncSessionLocal", return_value=session)


class TestEarlyReturns:
    @pytest.mark.asyncio
    async def test_no_admin_email(self):
        with (
            patch("app.core.config.get_settings", return_value=_make_settings(admin_email=None)),
            patch("app.core.bootstrap.AsyncSessionLocal") as session_factory,
        ):
            await bootstrap_admin()
            session_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_admin_password(self):
        with (
            patch(
                "app.core.config.get_settings",
                return_value=_make_settings(admin_password=None),
            ),
            patch("app.core.bootstrap.AsyncSessionLocal") as session_factory,
        ):
            await bootstrap_admin()
            session_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_auth_disabled(self):
        with (
            patch(
                "app.core.config.get_settings",
                return_value=_make_settings(local_auth_enabled=False),
            ),
            patch("app.core.bootstrap.AsyncSessionLocal") as session_factory,
        ):
            await bootstrap_admin()
            session_factory.assert_not_called()


class TestAdvisoryLock:
    @pytest.mark.asyncio
    async def test_xact_lock_is_first_statement(self):
        session = _FakeSession([_ScalarResult(scalar_one_or_none=MagicMock())])
        with (
            patch("app.core.config.get_settings", return_value=_make_settings()),
            _patch_session(session),
        ):
            await bootstrap_admin()
        first_sql = str(session.executed[0][0])
        assert "pg_advisory_xact_lock" in first_sql
        assert "pg_try_advisory_lock" not in first_sql


class TestExistingUser:
    @pytest.mark.asyncio
    async def test_existing_user_password_preserved_by_default(self):
        existing = MagicMock(password_hash="$argon2id$existing-hash$")
        # первый элемент — результат xact-lock (код его не читает)
        session = _FakeSession([_ScalarResult(), _ScalarResult(scalar_one_or_none=existing)])
        with (
            patch("app.core.config.get_settings", return_value=_make_settings()),
            patch("app.core.bootstrap.hash_password") as hash_pw,
            _patch_session(session),
        ):
            await bootstrap_admin()
        hash_pw.assert_not_called()
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_existing_user_password_reset_flag_overwrites(self):
        existing = MagicMock(password_hash="$argon2id$existing-hash$")
        session = _FakeSession(
            [
                _ScalarResult(scalar_one_or_none=existing),
            ]
        )
        with (
            patch(
                "app.core.config.get_settings",
                return_value=_make_settings(admin_password_reset_on_start=True),
            ),
            patch("app.core.bootstrap.hash_password", return_value="new-hash") as hash_pw,
            _patch_session(session),
        ):
            await bootstrap_admin()
        hash_pw.assert_called_once()
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_existing_user_without_password_hash_gets_one(self):
        existing = MagicMock(password_hash=None)
        session = _FakeSession(
            [
                _ScalarResult(scalar_one_or_none=existing),
            ]
        )
        with (
            patch("app.core.config.get_settings", return_value=_make_settings()),
            patch("app.core.bootstrap.hash_password", return_value="bootstrapped") as hash_pw,
            _patch_session(session),
        ):
            await bootstrap_admin()
        hash_pw.assert_called_once()
        assert session.commits == 1


class TestCreateAdmin:
    @pytest.mark.asyncio
    async def test_another_admin_exists_skip_create(self):
        other_admin = MagicMock(spec=[])
        session = _FakeSession(
            [
                _ScalarResult(),  # xact-lock
                _ScalarResult(scalar_one_or_none=None),
                _ScalarResult(scalar_one_or_none=other_admin),
            ]
        )
        with (
            patch("app.core.config.get_settings", return_value=_make_settings()),
            patch("app.core.bootstrap.hash_password") as hash_pw,
            _patch_session(session),
        ):
            await bootstrap_admin()
        hash_pw.assert_not_called()
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_creates_admin_when_table_empty(self):
        session = _FakeSession(
            [
                _ScalarResult(),  # xact-lock
                _ScalarResult(scalar_one_or_none=None),
                _ScalarResult(scalar_one_or_none=None),
            ]
        )
        with (
            patch("app.core.config.get_settings", return_value=_make_settings()),
            patch("app.core.bootstrap.hash_password", return_value="hashed") as hash_pw,
            _patch_session(session),
        ):
            await bootstrap_admin()
        hash_pw.assert_called_once_with("secret-pw-12345")
        assert session.commits == 1


class TestNoExplicitUnlock:
    @pytest.mark.asyncio
    async def test_advisory_unlock_never_executed(self):
        """Лок освобождает COMMIT: явный unlock после commit попадал на
        случайное соединение пула — источник утечки лока (2026-08-28)."""
        session = _FakeSession(
            [
                _ScalarResult(),  # xact-lock
                _ScalarResult(scalar_one_or_none=None),
                _ScalarResult(scalar_one_or_none=None),
            ]
        )
        with (
            patch("app.core.config.get_settings", return_value=_make_settings()),
            patch("app.core.bootstrap.hash_password", return_value="hashed"),
            _patch_session(session),
        ):
            await bootstrap_admin()
        for stmt, _params in session.executed:
            assert "pg_advisory_unlock" not in str(stmt)
