"""Общие фикстуры для всех тестов.

Структура:
- Env vars (setdefault, не перезаписывают реальные значения CI)
- Фабрики моделей (User, News, KbArticle, ServiceLink, Bookmark)
- Async DB-фикстуры (engine, session с rollback) — используются integration-тестами
- Async Redis-фикстура (с FLUSHDB после теста)
- TestClient/AsyncClient фикстуры с dependency_overrides
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio

# ── Env vars ─────────────────────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test_secret_key_that_is_32_chars_long_ok")
os.environ.setdefault("KEYCLOAK_URL", "http://keycloak:8080")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test_secret")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOCAL_AUTH_ENABLED", "true")
os.environ.setdefault("ADMIN_EMAIL", "")
os.environ.setdefault("ADMIN_PASSWORD", "")
os.environ.setdefault("PORTAL_BASE_URL", "http://test")


# ── Утилиты выявления интеграционного окружения ─────────────────────────────
def _is_integration_db_available() -> bool:
    """Проверка, можно ли подключиться к реальной PG (для conditional skip)."""
    return os.environ.get("INTEGRATION_DB", "false").lower() in ("1", "true", "yes")


def _is_integration_redis_available() -> bool:
    return os.environ.get("INTEGRATION_REDIS", "false").lower() in ("1", "true", "yes")


# ── event loop ──────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Session-scoped event loop — нужен для async фикстур с scope=session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── FastAPILimiter no-op stub for unit tests ────────────────────────────────
@pytest.fixture(autouse=True, scope="session")
def _stub_fastapi_limiter():
    """Подменяет `RateLimiter.__call__` no-op'ом для unit-тестов, чтобы endpoints
    с `Depends(RateLimiter(...))` не падали с
    'You must call FastAPILimiter.init in startup event of fastapi'.

    fakeredis не поддерживает Lua SCRIPT, который использует FastAPILimiter,
    поэтому полная инициализация в unit-тестах невозможна. Реальный rate-limit
    покрывают integration-тесты (test_rate_limit.py) с настоящим Redis.
    """
    try:
        from fastapi_limiter.depends import RateLimiter
    except ImportError:
        yield
        return

    original_call = RateLimiter.__call__

    async def _noop(self, request, response):  # type: ignore[no-untyped-def]
        return None

    RateLimiter.__call__ = _noop  # type: ignore[method-assign]
    yield
    RateLimiter.__call__ = original_call  # type: ignore[method-assign]


# ── DB-фикстуры (integration) ───────────────────────────────────────────────
@pytest_asyncio.fixture(scope="session")
async def _engine():
    """Async engine для integration-тестов. Skip если БД недоступна."""
    if not _is_integration_db_available():
        pytest.skip("INTEGRATION_DB=true required")

    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine) -> AsyncGenerator[Any, None]:
    """Каждый тест получает свежую сессию с rollback в finally.

    Использует SAVEPOINT (nested transaction) — изменения не утекают между тестами.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    async with _engine.connect() as conn:
        trans = await conn.begin()
        async_session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield async_session
        finally:
            await async_session.close()
            await trans.rollback()


# ── Redis-фикстура (integration) ────────────────────────────────────────────
@pytest_asyncio.fixture
async def redis_client():
    """Чистый Redis-клиент. FLUSHDB перед и после теста."""
    if not _is_integration_redis_available():
        pytest.skip("INTEGRATION_REDIS=true required")

    from redis.asyncio import Redis
    from app.core.config import get_settings

    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


# ── Фабрики ─────────────────────────────────────────────────────────────────
@pytest.fixture
def user_factory():
    """Фабрика для in-memory User (SimpleNamespace, для unit тестов)."""
    from types import SimpleNamespace

    def _make(
        role: str = "reader",
        department: str = "IT",
        auth_source: str = "local",
        **overrides: Any,
    ):
        defaults = {
            "id": uuid.uuid4(),
            "keycloak_id": None if auth_source == "local" else str(uuid.uuid4()),
            "email": f"{role}-{uuid.uuid4().hex[:6]}@portal.local",
            "full_name": f"Test {role.title()}",
            "department": department,
            "position": "Engineer",
            "phone": None,
            "role": role,
            "auth_source": auth_source,
            "password_hash": None,
            "avatar_url": None,
            "presence_status": "office",
            "notify_email": True,
            "notify_inapp": True,
            "lang": "ru",
            "preferences": {},
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "last_login_at": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return _make


@pytest.fixture
def news_factory():
    """Фабрика для in-memory News."""
    from types import SimpleNamespace

    def _make(**overrides: Any):
        defaults = {
            "id": uuid.uuid4(),
            "title": "Test news",
            "body": "<p>Test body</p>",
            "status": "published",
            "is_pinned": False,
            "category": None,
            "target_departments": None,
            "target_roles": None,
            "author_id": uuid.uuid4(),
            "publish_at": None,
            "archive_at": None,
            "published_at": datetime.now(UTC),
            "cover_image": None,
            "view_count": 0,
            "current_version": 1,
            "deleted_at": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return _make


@pytest.fixture
def kb_article_factory():
    """Фабрика для in-memory KbArticle."""
    from types import SimpleNamespace

    def _make(**overrides: Any):
        defaults = {
            "id": uuid.uuid4(),
            "title": "Test article",
            "body": "# Hello",
            "status": "draft",
            "version": 1,
            "view_count": 0,
            "published_at": None,
            "deleted_at": None,
            "section_id": None,
            "created_by": uuid.uuid4(),
            "updated_by": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "tags": [],
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return _make


# ── FastAPI app + клиент ────────────────────────────────────────────────────
@pytest.fixture
def app(monkeypatch):
    """Импортирует app.main с отключённым bootstrap admin (нет DB-вызовов в lifespan).

    Дополнительно инициализирует ``app.state.redis`` фейковым клиентом (fakeredis),
    чтобы middleware и handler'ы, обращающиеся к ``request.app.state.redis``, не падали
    с AttributeError при тестировании через ASGITransport (lifespan не запускается).
    """
    monkeypatch.setenv("ADMIN_EMAIL", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("LOCAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")

    import importlib

    from app.core.config import get_settings

    get_settings.cache_clear()

    import app.main as main_mod

    importlib.reload(main_mod)

    try:
        import fakeredis.aioredis as fakeredis_aio

        main_mod.app.state.redis = fakeredis_aio.FakeRedis(decode_responses=True)
    except ImportError:
        pass

    return main_mod.app


@pytest_asyncio.fixture
async def client(app):
    """AsyncClient с ASGITransport — без сетевых вызовов."""
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test"},  # CSRF-friendly
    ) as ac:
        yield ac


@pytest.fixture
def authed_client_factory(app, user_factory):
    """Возвращает фабрику authed AsyncClient'ов, переопределяющую get_current_user.

    Дополнительно переопределяет ``get_db`` фейковой AsyncSession-заглушкой,
    чтобы handler'ы, обращающиеся к БД, не падали при отсутствии Postgres
    (security-тесты проверяют только authz/HTTP-уровень, без бизнес-логики).
    """
    from unittest.mock import AsyncMock, MagicMock

    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_current_user, get_db

    created_clients: list = []

    async def _fake_db():
        session = MagicMock()
        result = MagicMock()
        result.scalar_one = MagicMock(return_value=0)
        result.scalar_one_or_none = MagicMock(return_value=None)
        result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]), first=MagicMock(return_value=None))
        )
        result.all = MagicMock(return_value=[])
        result.first = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        yield session

    def _make(role: str = "reader", **user_kwargs):
        user = user_factory(role=role, **user_kwargs)

        async def _fake_user():
            return user

        app.dependency_overrides[get_current_user] = _fake_user
        app.dependency_overrides[get_db] = _fake_db

        transport = ASGITransport(app=app)
        ac = AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test"},
        )
        created_clients.append(ac)
        return ac, user

    yield _make

    # cleanup
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)
    for ac in created_clients:
        try:
            asyncio.get_event_loop().run_until_complete(ac.aclose())
        except Exception:
            pass


# ── Маркеры ─────────────────────────────────────────────────────────────────
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests requiring real PG and/or Redis (INTEGRATION_DB / INTEGRATION_REDIS env vars)",
    )
    config.addinivalue_line("markers", "security: security/CSRF/headers/XSS tests")
    config.addinivalue_line("markers", "slow: tests that take >1s")
