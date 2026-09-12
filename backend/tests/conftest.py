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
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from fastapi import Request, Response

# ── Env vars ─────────────────────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test_secret_key_that_is_32_chars_long_ok")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOCAL_AUTH_ENABLED", "true")
os.environ.setdefault("ADMIN_EMAIL", "")
os.environ.setdefault("ADMIN_PASSWORD", "")
# PORTAL_BASE_URL is no longer an env var (see ADR-037). Tests get a
# `system.json` stub via the `_stub_system_settings` autouse session fixture
# below, which sets portal_base_url=http://test for CORS/auth.


# ── Утилиты выявления интеграционного окружения ─────────────────────────────
def _is_integration_db_available() -> bool:
    """Проверка, можно ли подключиться к реальной PG (для conditional skip)."""
    return os.environ.get("INTEGRATION_DB", "false").lower() in ("1", "true", "yes")


def _is_integration_redis_available() -> bool:
    return os.environ.get("INTEGRATION_REDIS", "false").lower() in ("1", "true", "yes")


def _is_nightly() -> bool:
    return os.environ.get("NIGHTLY", "false").lower() in ("1", "true", "yes")


# ── Nightly/daily skip-гейты (аудит 2026-08-21 P0.5 + audit-review follow-up²) ──
# Nightly-контур обещает полный охват: любой skip (включая collection) проваливает прогон.
# Daily-контур: runtest-skip'ы допустимы по бюджету (контур + причина + потолок);
# collection-skip'и (module-level importorskip) — ВНЕ бюджета причин: разрешены
# только точными путями из allowlist'а (follow-up² P1: раньше запись
# «[COLLECTION] ...: NIGHTLY=true required» проходила reason-подстрочный матчинг).
# Бюджет синхронизирован с docs/testing.md §«Skip-бюджет».
_nightly_skips: list[str] = []


@dataclass(frozen=True)
class _SkipRecord:
    nodeid: str
    reason: str
    rendered: str


_daily_skips: list[_SkipRecord] = []
_collect_skips: list[str] = []

# (контур, причина) → потолок. Контур определяется по префиксу nodeid —
# потолки независимы: рост nightly-skip'ов в integration не прячется за
# лимитом unit-контура (follow-up² P2). 0 = недопустимо в этом контуре.
_SKIP_CAP_UNLIMITED = -1

_DAILY_SKIP_CAPS: dict[tuple[str, str], int] = {
    # 6 → 10 (инкремент 6 learning, 2026-08-29): в TestRenderNginxConfigsScript
    # добавлены 4 теста рендера learn_server.conf (ADR-051) — та же природа,
    # что у прежних 6: subprocess render-config.sh, nightly-only.
    # 10 → 12 (remediation-волна 1, 2026-09-02): +2 теста того же класса —
    # fail-closed http://-рендер learn-контура (PA-025) и порядок
    # learner-allowlist (PA-003). Новые render-тесты => поднимай потолок здесь.
    ("unit", "nightly marker: set NIGHTLY=true to run"): 12,
    ("integration", "nightly marker: set NIGHTLY=true to run"): 1,  # test_migrations.py:341
    ("unit", "NIGHTLY=true required"): 0,
    ("integration", "NIGHTLY=true required"): 1,  # test_migrations_nightly.py:36
    # в integration-контуре стек поднят — INTEGRATION_*-skip'ов быть не должно
    ("integration", "INTEGRATION_DB=true required"): 0,
    ("integration", "INTEGRATION_REDIS=true required"): 0,
    # unit-контур: INTEGRATION_* без потолка, но только тестам с маркером
    # unit_with_db (follow-up² P2: принадлежность маркеру проверяется кодом)
    ("unit", "INTEGRATION_DB=true required"): _SKIP_CAP_UNLIMITED,
    ("unit", "INTEGRATION_REDIS=true required"): _SKIP_CAP_UNLIMITED,
}

# Module-level skip (pytest.importorskip / pytest.skip на импорте) допустим
# ТОЛЬКО для точных путей. Пусто: сегодня collection-skip'ов нет — любой
# новый (например, исчезнувшая зависимость) провалит прогон.
_COLLECT_SKIP_ALLOWED_MODULES: frozenset[str] = frozenset()

# nodeid → есть ли у теста маркер unit_with_db (снимок на коллекции)
_UNIT_WITH_DB_TESTS: set[str] = set()
_NIGHTLY_TESTS: set[str] = set()


def _context_of(nodeid: str) -> str:
    for prefix in ("tests/unit/", "tests/integration/", "tests/security/"):
        if nodeid.startswith(prefix):
            return prefix.rstrip("/").split("/")[-1]
    return "other"


def _skip_reason(longrepr: object) -> str:
    """Извлечь точную pytest skip-причину без путей/исходников longrepr."""
    if isinstance(longrepr, tuple) and len(longrepr) >= 3:
        reason = str(longrepr[2])
    else:
        reason = str(longrepr)
    return reason.removeprefix("Skipped: ")


def _budget_violations() -> list[str]:
    unexpected: list[str] = []
    counts: dict[tuple[str, str], int] = {}
    allowed_reasons = {reason for _, reason in _DAILY_SKIP_CAPS}
    for record in _daily_skips:
        context = _context_of(record.nodeid)
        reason = record.reason if record.reason in allowed_reasons else None
        if reason is None:
            unexpected.append(record.rendered)
            continue
        key = (context, reason)
        counts[key] = counts.get(key, 0) + 1
        if (
            reason
            in {
                "nightly marker: set NIGHTLY=true to run",
                "NIGHTLY=true required",
            }
            and record.nodeid not in _NIGHTLY_TESTS
        ):
            unexpected.append(
                f"[МАРКЕР] {record.rendered} — nightly-skip допустим только тестам "
                f"с @pytest.mark.nightly"
            )
        # unit-контур: INTEGRATION_* — только с маркером unit_with_db
        if (
            context == "unit"
            and reason.startswith("INTEGRATION_")
            and record.nodeid not in _UNIT_WITH_DB_TESTS
        ):
            unexpected.append(
                f"[МАРКЕР] {record.rendered} — INTEGRATION_*-skip в unit-контуре допустим "
                f"только тестам с @pytest.mark.unit_with_db"
            )
    for (context, reason), count in counts.items():
        cap = _DAILY_SKIP_CAPS.get((context, reason))
        if cap is None:
            # причины нет в таблице для этого контура → запрещена здесь
            unexpected.append(f"[КОНТУР] причина «{reason}» в контуре «{context}» вне бюджета")
        elif cap == 0:
            unexpected.append(
                f"[КОНТУР] причина «{reason}» в контуре «{context}» недопустима ({count} skip(ов))"
            )
        elif cap > 0 and count > cap:
            unexpected.append(
                f"[БЮДЖЕТ] контур «{context}», причина «{reason}»: {count} skip(ов) "
                f"> потолка {cap} — правка _DAILY_SKIP_CAPS должна быть осознанной"
            )
    return unexpected


def pytest_collectreport(report) -> None:
    """Collection-skip'ы — ВНЕ reason-бюджета: только точный allowlist."""
    if report.skipped:
        nodeid = str(getattr(report, "nodeid", "") or report.fspath)
        entry = f"{nodeid}: {report.longrepr}"
        if _is_nightly():
            _nightly_skips.append(entry)
        elif nodeid not in _COLLECT_SKIP_ALLOWED_MODULES:
            _collect_skips.append(entry)


def pytest_runtest_logreport(report) -> None:
    properties = dict(getattr(report, "user_properties", ()))
    if properties.get("portal_unit_with_db") is True:
        _UNIT_WITH_DB_TESTS.add(report.nodeid)
    if properties.get("portal_nightly") is True:
        _NIGHTLY_TESTS.add(report.nodeid)
    if report.skipped:
        rendered = f"{report.nodeid}: {report.longrepr}"
        if _is_nightly():
            _nightly_skips.append(rendered)
        else:
            _daily_skips.append(
                _SkipRecord(
                    nodeid=report.nodeid,
                    reason=_skip_reason(report.longrepr),
                    rendered=rendered,
                )
            )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Передать marker metadata от xdist worker контроллеру вместе с report."""
    outcome = yield
    report = outcome.get_result()
    if item.get_closest_marker("unit_with_db") is not None:
        report.user_properties.append(("portal_unit_with_db", True))
    if item.get_closest_marker("nightly") is not None:
        report.user_properties.append(("portal_nightly", True))


def pytest_sessionfinish(session, exitstatus) -> None:
    if _is_nightly():
        if _nightly_skips:
            print(f"\n{'=' * 60}")
            print(f"NIGHTLY=true: {len(_nightly_skips)} неожиданных skip(ов) — прогон провален.")
            print("Бюджет допустимых skip-причин: docs/testing.md §«Skip-бюджет».")
            for entry in _nightly_skips:
                print(f"  SKIPPED {entry}")
            print("=" * 60)
            session.exitstatus = 1
        return

    unexpected = _budget_violations() + [f"[COLLECTION] {e}" for e in _collect_skips]
    if unexpected:
        print(f"\n{'=' * 60}")
        print(f"{len(unexpected)} skip-нарушений бюджета — прогон провален.")
        print("Бюджет: docs/testing.md §«Skip-бюджет» + _DAILY_SKIP_CAPS в tests/conftest.py.")
        for entry in unexpected:
            print(f"  SKIPPED {entry}")
        print("=" * 60)
        session.exitstatus = 1


# ── event loop ──────────────────────────────────────────────────────────────
# Управляется через `asyncio_default_fixture_loop_scope = "session"` в pyproject.toml
# (pytest-asyncio ≥ 0.23). Кастомный `event_loop` фикстуру держать не нужно —
# она deprecated и удалена в pytest-asyncio 0.24+.


# ── system.json stub (test-friendly SystemSettings) ─────────────────────────
@pytest.fixture(autouse=True, scope="session")
def _stub_system_settings(tmp_path_factory):
    """Redirect `_SYSTEM_SETTINGS_FILE` to a tmp file pre-populated with
    test-friendly values so that load_system_settings() returns
    portal_base_url=http://test (used by CORS/CSRF/auth) without depending on
    /data/settings being writable on the test host.
    """
    from app.core import system_config
    from app.core.system_config import SystemSettings

    tmp_dir = tmp_path_factory.mktemp("settings")
    tmp_file = tmp_dir / "system.json"
    test_settings = SystemSettings(
        portal_base_url="http://test",
        nextcloud_url="http://nextcloud:8080",
        nc_service_app_password="test_password",
    )
    tmp_file.write_text(test_settings.model_dump_json(), encoding="utf-8")

    original_file = system_config._SYSTEM_SETTINGS_FILE
    original_dir = system_config._SETTINGS_DIR
    system_config._SYSTEM_SETTINGS_FILE = tmp_file
    system_config._SETTINGS_DIR = tmp_dir
    system_config._settings_cache.clear()
    try:
        yield
    finally:
        system_config._SYSTEM_SETTINGS_FILE = original_file
        system_config._SETTINGS_DIR = original_dir
        system_config._settings_cache.clear()


# ── Global module/settings cache isolation ─────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_runtime_config_caches():
    """Reset module-level config caches before/after every test.

    `load_modules()` (app.core.modules_config) and `load_system_settings()`
    (app.core.system_config) memoise results in process-global dicts with a
    60s TTL. With `pytest-randomly`, a test that populates these caches (e.g.
    enabling Nextcloud) leaks state into later tests — most notably the
    `/ready` health probe, which then performs a Nextcloud health check and
    returns 503. Clearing the caches per-test keeps tests deterministic
    regardless of execution order.
    """
    from app.core.modules_config import invalidate_modules_cache
    from app.core.system_config import invalidate_settings_cache

    invalidate_modules_cache()
    invalidate_settings_cache()
    try:
        yield
    finally:
        invalidate_modules_cache()
        invalidate_settings_cache()


# ── FastAPILimiter no-op stub for unit tests ────────────────────────────────
# ВАЖНО: импортируем `app.core.limiter` ДО чтения `RateLimiter.__call__`.
# Патч ADR-043 (совместимость fastapi-limiter 0.1.6 со starlette 1.x —
# `_IncludedRouter` не имеет атрибута `path`) применяется при импорте модуля.
# Если conftest загрузится раньше `app.main` (как в CI), без этого форсированного
# импорта `_real_rate_limiter_call` укажет на оригинальный (непатченный) `__call__`,
# и integration-тесты, восстанавливая его в `RateLimiter.__call__ = saved_call`,
# затрут патч → `AttributeError: '_IncludedRouter' object has no attribute 'path'`
# на всех rate-limited endpoints (login/refresh/search/password).
try:
    from fastapi_limiter.depends import RateLimiter as _RateLimiter

    from app.core.limiter import patched_call as _adr043_patched_call  # noqa: F401

    _real_rate_limiter_call: Any = _RateLimiter.__call__
except ImportError:
    _real_rate_limiter_call = None


@pytest.fixture(autouse=True, scope="session")
def _stub_fastapi_limiter():
    """Подменяет `RateLimiter.__call__` no-op'ом для unit-тестов, чтобы endpoints
    с `Depends(RateLimiter(...))` не падали с
    'You must call FastAPILimiter.init in startup event of fastapi'.

    fakeredis не поддерживает Lua SCRIPT, который использует FastAPILimiter,
    поэтому полная инициализация в unit-тестах невозможна. Реальный rate-limit
    покрывают integration-тесты (test_rate_limit.py) с настоящим Redis.
    """
    if _real_rate_limiter_call is None:
        yield
        return

    from fastapi_limiter.depends import RateLimiter

    async def _noop(self, request: Request, response: Response) -> None:  # type: ignore[override]
        return None

    RateLimiter.__call__ = _noop  # type: ignore[method-assign]
    yield
    RateLimiter.__call__ = _real_rate_limiter_call  # type: ignore[method-assign]


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
# Полные in-memory инстансы SQLAlchemy-моделей через polyfactory.SQLAlchemyFactory.
# Сохраняет историческую `_make(**overrides)`-семантику фикстур, но автоматически
# синхронизируется с актуальной схемой моделей (новые/удалённые колонки,
# server_default'ы) — больше не нужно вручную править SimpleNamespace.
import contextlib

from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.dialects.postgresql import TSVECTOR

from app.models.kb import KbArticle
from app.models.news import News
from app.models.user import User


def _drop_tsvector_columns(cls, column):
    """`SQLAlchemyFactory.get_type_from_column` overrides для PG-TSVECTOR.

    Polyfactory не знает, как генерировать `TSVECTOR` (Computed/GIN-индексы),
    поэтому для таких колонок возвращаем `type(None)` — fabric проставит `None`,
    что корректно для in-memory объектов (БД сама посчитает tsvector).
    """
    if isinstance(column.type, TSVECTOR):
        return type(None)
    return _drop_tsvector_columns._orig(cls, column)


_drop_tsvector_columns._orig = SQLAlchemyFactory.get_type_from_column.__func__  # type: ignore[attr-defined]
SQLAlchemyFactory.get_type_from_column = classmethod(_drop_tsvector_columns)  # type: ignore[method-assign,assignment]


class _UserFactory(SQLAlchemyFactory[User]):
    __model__ = User
    __set_relationships__ = False


class _NewsFactory(SQLAlchemyFactory[News]):
    __model__ = News
    __set_relationships__ = False


class _KbArticleFactory(SQLAlchemyFactory[KbArticle]):
    __model__ = KbArticle
    __set_relationships__ = False


@pytest.fixture
def user_factory():
    """In-memory `User` через polyfactory; sane defaults для unit-тестов."""

    def _make(
        role: str = "reader",
        department: str = "IT",
        auth_source: str = "local",
        **overrides: Any,
    ) -> User:
        defaults: dict[str, Any] = {
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
            "current_status": "working",
            "notify_email": True,
            "notify_inapp": True,
            "lang": "ru",
            "preferences": {},
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "last_login_at": None,
            "deleted_at": None,
        }
        defaults.update(overrides)
        return _UserFactory.build(**defaults)

    return _make


@pytest.fixture
def news_factory():
    """In-memory `News` через polyfactory."""

    def _make(**overrides: Any) -> News:
        defaults: dict[str, Any] = {
            "id": uuid.uuid4(),
            "title": "Test news",
            "body": "<p>Test body</p>",
            "status": "published",
            "is_pinned": False,
            "categories": [],
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
        return _NewsFactory.build(**defaults)

    return _make


@pytest.fixture
def kb_article_factory():
    """In-memory `KbArticle` через polyfactory."""

    def _make(**overrides: Any) -> KbArticle:
        defaults: dict[str, Any] = {
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
        }
        defaults.update(overrides)
        return _KbArticleFactory.build(**defaults)

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


_CSRF_TOKEN = "test-csrf-token-for-unit-tests"


@pytest_asyncio.fixture
async def client(app):
    """AsyncClient с ASGITransport — без сетевых вызовов."""
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
        cookies={"XSRF-TOKEN": _CSRF_TOKEN},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def authed_client_factory(app, user_factory):
    """Возвращает фабрику authed AsyncClient'ов, переопределяющую get_current_user.

    ВНИМАНИЕ: дополнительно переопределяет ``get_db`` no-op заглушкой
    (``_fake_db``), которая на любой ``session.execute()`` возвращает
    пустые результаты (``scalar_one=0``, ``all=[]``, ``first=None``).
    Это значит:

    * Endpoints, реально зависящие от данных в БД, могут вернуть 200/204
      там, где в проде упали бы — поэтому бизнес-сценарии этой фикстурой
      проверять НЕЛЬЗЯ.
    * Допустимое применение — только security/authz/HTTP-уровень
      (см. ``security_authed_client_factory`` в ``tests/security/conftest.py``).

    Бизнес-логику проверяйте через ``real_db_session`` из
    ``tests/integration/conftest.py`` (реальный Postgres + SAVEPOINT).

    Список текущих unit-тестов, использующих эту фикстуру, зафиксирован
    в CI grep-gate (job ``fake-db-allowlist`` в ``.github/workflows/ci.yml``);
    новые unit-тесты добавлять туда не допускается — переводите сразу
    на integration.
    """
    from unittest.mock import AsyncMock, MagicMock

    from httpx import ASGITransport, AsyncClient

    from app.api.deps import (
        get_current_user,
        get_db,
        get_session_factory,
        get_user_for_refresh,
    )

    created_clients: list = []

    async def _fake_db():
        session = MagicMock()
        result = MagicMock()
        result.scalar_one = MagicMock(return_value=0)
        result.scalar_one_or_none = MagicMock(return_value=None)
        result.scalars = MagicMock(
            return_value=MagicMock(
                all=MagicMock(return_value=[]), first=MagicMock(return_value=None)
            )
        )
        result.mappings = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
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
        app.dependency_overrides[get_user_for_refresh] = _fake_user
        if get_db not in app.dependency_overrides:
            app.dependency_overrides[get_db] = _fake_db

        def _fake_session_factory():
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _ctx():
                # Используем текущую активную подмену get_db (она может быть
                # переопределена внутри конкретного теста); fallback — _fake_db.
                db_override = app.dependency_overrides.get(get_db, _fake_db)
                gen = db_override()
                sess = await gen.__anext__()
                try:
                    yield sess
                finally:
                    with contextlib.suppress(StopAsyncIteration):
                        await gen.__anext__()

            return _ctx()

        if get_session_factory not in app.dependency_overrides:
            app.dependency_overrides[get_session_factory] = lambda: _fake_session_factory

        transport = ASGITransport(app=app)
        ac = AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
            cookies={"XSRF-TOKEN": _CSRF_TOKEN},
        )
        created_clients.append(ac)
        return ac, user

    yield _make

    # cleanup
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_user_for_refresh, None)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_session_factory, None)
    for ac in created_clients:
        with contextlib.suppress(Exception):
            await ac.aclose()


# ── Concurrency helpers ──────────────────────────────────────────────────────
@pytest.fixture
def concurrent_tasks():
    """Fixture for simulating multi-worker race conditions within a single event loop.

    Returns an async helper that runs N copies of a coroutine factory concurrently
    using asyncio.gather and collects all results/exceptions.

    Usage::

        async def test_idempotency(concurrent_tasks):
            results = await concurrent_tasks(
                lambda i: some_coroutine(worker_id=i),
                count=10,
            )
            # Each result is either the return value or the exception raised

    The fixture deliberately uses gather(return_exceptions=True) so individual
    failures don't abort sibling tasks — all N outcomes are returned for assertion.
    """

    async def _run(factory, *, count: int = 2):
        coros = [factory(i) for i in range(count)]
        return await asyncio.gather(*coros, return_exceptions=True)

    return _run


# ── Маркеры ─────────────────────────────────────────────────────────────────
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests requiring real PG and/or Redis (INTEGRATION_DB / INTEGRATION_REDIS env vars)",
    )
    config.addinivalue_line("markers", "security: security/CSRF/headers/XSS tests")
    config.addinivalue_line("markers", "slow: tests that take >1s")
    config.addinivalue_line(
        "markers",
        "unit_with_db: unit-style test that needs real PG (REVIEW-2.1 migration path); "
        "fixtures `real_db_session`/`real_user`/`real_editor`/`real_admin` auto-skip "
        "via pytest.skip when INTEGRATION_DB is not true",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip `nightly`-marked tests unless NIGHTLY=true.

    Симметрично с integration-маркером: тяжёлые/зависящие от окружения тесты
    (например, nginx render-config.sh, требующий jq/envsubst/POSIX sh) помечаются
    `@pytest.mark.nightly` и гоняются только в nightly-CI. В обычных прогонах
    (unit/security) они auto-skip'аются с понятной причиной, а не падают с
    "jq not available" — это убирает шум из daily-отчётов и делает skip-причину
    самодокументируемой (см. ADR про маркеры в pyproject.toml).
    """
    if os.environ.get("NIGHTLY", "false").lower() in ("1", "true", "yes"):
        return
    nightly_skip = pytest.mark.skip(reason="nightly marker: set NIGHTLY=true to run")
    for item in items:
        if item.get_closest_marker("unit_with_db") is not None:
            _UNIT_WITH_DB_TESTS.add(item.nodeid)
        if item.get_closest_marker("nightly") is not None:
            _NIGHTLY_TESTS.add(item.nodeid)
        if item.get_closest_marker("nightly") is not None:
            item.add_marker(nightly_skip)


# ── Shared DB fixtures (REVIEW-2.1) ─────────────────────────────────────────
# Re-export from tests/db_fixtures.py so that any test (unit, integration, security)
# can request `real_db_session`/`real_user`/`real_editor`/`real_admin`. Fixtures
# self-skip when INTEGRATION_DB is not set, so importing here is safe for pure
# unit prog­ons — they remain no-op unless explicitly required by a test.
from tests.db_fixtures import (  # noqa: F401
    real_admin,
    real_db_engine,
    real_db_session,
    real_editor,
    real_user,
)
