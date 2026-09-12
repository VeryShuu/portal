"""Integration: local auth — реальный HTTP + PostgreSQL + Redis (DSN-стек).

Переписан по аудиту тестирования 2026-08-21 (docs/wip/test-audit-remediation.md,
PR 2): прежняя версия проверяла таутологии на словарях/MagicMock и не вызывала
production-код вообще. Теперь эндпоинты login/logout/me и функция bootstrap_admin
проверяются через наблюдаемое поведение: реальный POST через ASGITransport,
реальная БД (docker-compose.test.yml) и реальный Redis.

Запуск: ./scripts/test-integration.sh tests/integration/test_local_auth.py

Rate-limit здесь сознательно не проверяется (отдельный контур —
tests/integration/test_rate_limit.py): запросы идут с X-Real-IP из доверенной
docker-internal подсети 172.16.0.0/12 (probe-bypass), email-лимит не
накапливается благодаря уникальным email per test.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# X-Real-IP из доверенной internal-подсети: IP-лимит login пропускается
# (service-to-service путь, как у synthetic-пробы и CI e2e E2E_REAL_IP).
_TRUSTED_INTERNAL_IP = "172.16.0.42"


@pytest_asyncio.fixture
async def users_to_cleanup(real_db_engine: AsyncEngine) -> AsyncGenerator[list[str], None]:
    """Email'ы, созданных пользователей с которыми тест коммитится в БД.

    Эндпоинты и bootstrap_admin делают настоящие COMMIT — SAVEPOINT-изоляция
    здесь неприменима. Чистим явно (hard delete), чтобы не загрязнять БД
    (аудит 2026-08-21, P1: «integration-тесты могут загрязнять БД»).
    """
    from app.models.user import User

    emails: list[str] = []
    yield emails
    if emails:
        async with AsyncSession(real_db_engine, expire_on_commit=False) as s:
            await s.execute(delete(User).where(User.email.in_(emails)))
            await s.commit()


async def _create_user(
    real_db_engine: AsyncEngine,
    *,
    email: str,
    password: str | None,
    auth_source: str = "local",
    role: str = "reader",
) -> None:
    """Создать пользователя реальным COMMIT'ом (виден приложению)."""
    from app.core.security import hash_password
    from app.models.user import User

    async with AsyncSession(real_db_engine, expire_on_commit=False) as s:
        s.add(
            User(
                email=email,
                full_name="Local Auth Integration",
                role=role,
                auth_source=auth_source,
                password_hash=hash_password(password)
                if auth_source == "local" and password
                else None,
                current_status="working",
                notify_email=True,
                notify_inapp=True,
                lang="ru",
                preferences={},
                updated_at=datetime.now(UTC),
            )
        )
        await s.commit()


async def _fetch_user(real_db_engine: AsyncEngine, email: str) -> Any:
    from app.models.user import User

    async with AsyncSession(real_db_engine, expire_on_commit=False) as s:
        return (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()


def _prepare_bootstrap_env(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    *,
    email: str,
    password: str,
    local_enabled: str = "true",
) -> None:
    """Задать env для bootstrap_admin и сбросить кэш настроек.

    cache_clear нужен: bootstrap_admin читает get_settings() внутри вызова.
    Финализатор сбрасывает кэш ещё раз после теста — monkeypatch восстановит
    env, и следующий get_settings() увидит уже восстановленное окружение.
    """
    from app.core.config import get_settings

    monkeypatch.setenv("ADMIN_EMAIL", email)
    monkeypatch.setenv("ADMIN_PASSWORD", password)
    monkeypatch.setenv("LOCAL_AUTH_ENABLED", local_enabled)
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)


@pytest_asyncio.fixture
async def auth_app(app, redis_client):
    """Приложение с реальным Redis (не fakeredis из базовой фикстуры app).

    get_db НЕ переопределяется: эндпоинты используют собственный engine
    приложения, привязанный к DATABASE_URL тест-стека. Rate-limiter
    инициализируется как в production-lifespan (реальный Redis + патч ADR-043).
    """
    from fastapi_limiter import FastAPILimiter
    from fastapi_limiter.depends import RateLimiter

    import tests.conftest as _root_conftest
    from app.core.limiter import real_ip_identifier

    app.state.redis = redis_client
    saved_call = RateLimiter.__call__
    if _root_conftest._real_rate_limiter_call is not None:
        RateLimiter.__call__ = _root_conftest._real_rate_limiter_call  # type: ignore[method-assign]
    await FastAPILimiter.init(redis_client, identifier=real_ip_identifier)
    try:
        yield app
    finally:
        RateLimiter.__call__ = saved_call  # type: ignore[method-assign]
        with suppress(Exception):
            await FastAPILimiter.close()


@pytest_asyncio.fixture
async def auth_client(auth_app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test", "X-Real-IP": _TRUSTED_INTERNAL_IP},
    ) as ac:
        yield ac


class TestLocalLoginEndpoint:
    async def test_login_success_sets_session_and_cookies(
        self, auth_client, real_db_engine, users_to_cleanup
    ):
        """Успешный вход: 200, cookies сессии/метода входа, /auth/me видит пользователя."""
        from app.core.security import LAST_AUTH_METHOD_COOKIE, SESSION_COOKIE_NAME

        email = f"ok-{uuid.uuid4().hex[:8]}@portal.local"
        password = "Sup3rSecret!1"
        users_to_cleanup.append(email)
        await _create_user(real_db_engine, email=email, password=password)

        r = await auth_client.post(
            "/api/v1/auth/local/login", json={"email": email, "password": password}
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert r.json()["user_id"]
        # сессионная cookie + маркер способа входа (ADR-036 п.7)
        assert SESSION_COOKIE_NAME in r.cookies
        assert r.cookies.get(LAST_AUTH_METHOD_COOKIE) == "local"

        me = await auth_client.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["email"] == email
        assert me.json()["auth_source"] == "local"

        # last_login_at обновился в БД
        user = await _fetch_user(real_db_engine, email)
        assert user.last_login_at is not None

    async def test_login_wrong_password_401(self, auth_client, real_db_engine, users_to_cleanup):
        email = f"wrong-{uuid.uuid4().hex[:8]}@portal.local"
        users_to_cleanup.append(email)
        await _create_user(real_db_engine, email=email, password="RightPass!1")

        r = await auth_client.post(
            "/api/v1/auth/local/login", json={"email": email, "password": "WrongPass!2"}
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password"
        from app.core.security import SESSION_COOKIE_NAME

        assert SESSION_COOKIE_NAME not in r.cookies

    async def test_login_unknown_email_401(self, auth_client):
        r = await auth_client.post(
            "/api/v1/auth/local/login",
            json={"email": f"ghost-{uuid.uuid4().hex[:8]}@portal.local", "password": "Whatever!1"},
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password"

    async def test_keycloak_account_cannot_use_local_login(
        self, auth_client, real_db_engine, users_to_cleanup
    ):
        """Аккаунт Keycloak не может войти по паролю (401, не 500 — regression на DUMMY_HASH-путь)."""
        email = f"kc-{uuid.uuid4().hex[:8]}@portal.local"
        users_to_cleanup.append(email)
        await _create_user(real_db_engine, email=email, password=None, auth_source="keycloak")

        r = await auth_client.post(
            "/api/v1/auth/local/login", json={"email": email, "password": "SomePass!1"}
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password"

    async def test_login_rejects_disabled_local_auth(self, auth_client, monkeypatch):
        """LOCAL_AUTH_ENABLED=false → 403 до какой-либо проверки пароля."""
        from app.api.auth import local as local_module

        monkeypatch.setattr(local_module.settings, "local_auth_enabled", False)
        r = await auth_client.post(
            "/api/v1/auth/local/login",
            json={"email": "anyone@portal.local", "password": "Whatever!1"},
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "Local authentication is disabled"


class TestLogoutFlow:
    async def test_logout_invalidates_session_and_redirects_local(
        self, auth_client, real_db_engine, users_to_cleanup
    ):
        """Logout: сессия удаляется из Redis, redirect на /auth/local, cookie метода выживает."""
        from app.core.security import LAST_AUTH_METHOD_COOKIE

        email = f"out-{uuid.uuid4().hex[:8]}@portal.local"
        password = "LogoutPass!1"
        users_to_cleanup.append(email)
        await _create_user(real_db_engine, email=email, password=password)

        r = await auth_client.post(
            "/api/v1/auth/local/login", json={"email": email, "password": password}
        )
        assert r.status_code == 200
        from app.core.security import SESSION_COOKIE_NAME

        session_id = r.cookies.get(SESSION_COOKIE_NAME)
        assert session_id

        me = await auth_client.get("/api/v1/auth/me")
        assert me.status_code == 200

        out = await auth_client.post("/api/v1/auth/logout")
        assert out.status_code == 302
        assert out.headers["location"] == "/auth/local?logged_out=1"

        # сессия уничтожена: /auth/me больше не узнаёт пользователя
        me2 = await auth_client.get("/api/v1/auth/me")
        assert me2.status_code == 401
        # ...и старый session_id невалиден именно на СЕРВЕРЕ (Redis), а не только
        # удалён из cookie клиента — украденный/заскриншотенный id тоже мёртв
        auth_client.cookies.set(SESSION_COOKIE_NAME, session_id)
        me3 = await auth_client.get("/api/v1/auth/me")
        assert me3.status_code == 401
        # cookie способа входа намеренно переживает logout (ADR-036 п.7)
        assert auth_client.cookies.get(LAST_AUTH_METHOD_COOKIE) == "local"


class TestBootstrapAdmin:
    async def test_bootstrap_creates_first_admin(
        self, real_db_engine, users_to_cleanup, monkeypatch, request
    ):
        from app.core.security import verify_password

        email = f"bootstrap-{uuid.uuid4().hex[:8]}@portal.local"
        password = "B00tstrap!Pass"
        users_to_cleanup.append(email)
        _prepare_bootstrap_env(monkeypatch, request, email=email, password=password)

        from app.core.bootstrap import bootstrap_admin

        await bootstrap_admin()

        user = await _fetch_user(real_db_engine, email)
        assert user is not None, "bootstrap обязан создать первого админа"
        assert user.role == "admin"
        assert user.auth_source == "local"
        assert verify_password(password, user.password_hash) is True

    async def test_bootstrap_does_not_reset_changed_password(
        self, real_db_engine, users_to_cleanup, monkeypatch, request
    ):
        """Повторный вызов bootstrap НЕ откатывает пароль, сменённый через UI."""
        from app.core.bootstrap import bootstrap_admin
        from app.core.security import hash_password, verify_password
        from app.models.user import User

        email = f"keepass-{uuid.uuid4().hex[:8]}@portal.local"
        env_password = "EnvPass!12345"
        changed_password = "ChangedPass!678"
        users_to_cleanup.append(email)
        _prepare_bootstrap_env(monkeypatch, request, email=email, password=env_password)

        await bootstrap_admin()

        # администратор сменил пароль через UI
        async with AsyncSession(real_db_engine, expire_on_commit=False) as s:
            user = (await s.execute(select(User).where(User.email == email))).scalar_one()
            user.password_hash = hash_password(changed_password)
            await s.commit()

        # рестарт контейнера → bootstrap_admin снова
        await bootstrap_admin()

        user2 = await _fetch_user(real_db_engine, email)
        assert verify_password(changed_password, user2.password_hash) is True
        assert verify_password(env_password, user2.password_hash) is False

    async def test_bootstrap_skips_when_other_admin_exists(
        self, real_db_engine, users_to_cleanup, monkeypatch, request
    ):
        from app.core.bootstrap import bootstrap_admin

        existing_admin_email = f"admin-exist-{uuid.uuid4().hex[:8]}@portal.local"
        virgin_email = f"admin-virgin-{uuid.uuid4().hex[:8]}@portal.local"
        users_to_cleanup.extend([existing_admin_email, virgin_email])
        await _create_user(
            real_db_engine, email=existing_admin_email, password="AdminPass!1", role="admin"
        )
        _prepare_bootstrap_env(monkeypatch, request, email=virgin_email, password="Unused!12345")

        await bootstrap_admin()

        assert await _fetch_user(real_db_engine, virgin_email) is None, (
            "bootstrap не должен создавать второго админа из ADMIN_EMAIL, если админ уже есть"
        )

    async def test_bootstrap_skips_when_local_auth_disabled(
        self, real_db_engine, users_to_cleanup, monkeypatch, request
    ):
        from app.core.bootstrap import bootstrap_admin

        email = f"disabled-{uuid.uuid4().hex[:8]}@portal.local"
        users_to_cleanup.append(email)
        _prepare_bootstrap_env(
            monkeypatch, request, email=email, password="Unused!12345", local_enabled="false"
        )

        await bootstrap_admin()

        assert await _fetch_user(real_db_engine, email) is None
