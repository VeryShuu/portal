import contextlib
from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.system_config import load_system_settings

logger = get_logger(__name__)

settings = get_settings()
_sys = load_system_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle,
    echo=_sys.log_level.upper() == "DEBUG",
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ── Отдельный движок learning-роутов (ТЗ learning.md §10.8) ──────────────────
# Роль learning_app имеет гранты только на learning_*-таблицы + INSERT на
# email_outbox (миграция 102) — SQL-инъекция или баг в learning-коде не даёт
# доступа к штатным таблицам (users, news, ...). Пароль не задан (dev/тесты) —
# learning-роуты работают на общем движке; на проде LEARNING_DB_PASSWORD
# обязателен (см. .env.example).
LEARNING_DB_ROLE = "learning_app"


def _learning_database_url() -> str | None:
    if not settings.learning_db_password:
        return None
    url = make_url(settings.database_url)
    return url.set(
        username=LEARNING_DB_ROLE, password=settings.learning_db_password
    ).render_as_string(hide_password=False)


def _build_session_factory(target_url: str | None) -> async_sessionmaker[AsyncSession]:
    if target_url is None:
        return AsyncSessionLocal
    target_engine = create_async_engine(
        target_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle,
    )
    return async_sessionmaker(
        target_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


LearningSessionLocal = _build_session_factory(_learning_database_url())

_learning_engine_notice_shown = False


def _notice_learning_engine() -> None:
    """Однократный маркер режима learning-движка — при первом запросе
    learning-сессии, НЕ при импорте модуля: alembic-env импортирует этот
    модуль, и лог-строка при импорте попадает в stdout `alembic current`
    раньше ревизии — парсер migrate.sh читал дату вместо «107»
    (красный compose-smoke PR #161, 2026-08-30)."""
    global _learning_engine_notice_shown
    if _learning_engine_notice_shown:
        return
    _learning_engine_notice_shown = True
    if settings.learning_db_password:
        logger.info("learning.db_role_engine_enabled", role=LEARNING_DB_ROLE)
    else:
        # На проде это должно быть видно сразу: без пароля изоляция §10.8 не
        # действует (learning-роуты на общем привилегированном пуле). Сама
        # синхронизация пароля роли — scripts/ensure_learning_db_role.py (migrate.sh).
        logger.warning(
            "learning.db_role_engine_disabled",
            hint="LEARNING_DB_PASSWORD не задан — learning-роуты работают на общем движке",
        )


class Base(DeclarativeBase):
    pass


async def _managed_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with factory() as session:
        try:
            yield session
        except Exception:
            # Rollback-failure обязана прощаться: после серверной терминции
            # транзакции (deadlock 40P01, serialization failure) сессия
            # клинчится (IllegalStateChangeError на любом асинхронном вызове),
            # и ошибка rollback не должна маскировать исходное исключение —
            # иначе нормализованный 409 (meetings bookings) превращается в 500.
            # Соединение корректно утилизируется пулом (reset-on-return).
            with contextlib.suppress(Exception):
                await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in _managed_session(AsyncSessionLocal):
        yield session


async def get_learning_db() -> AsyncGenerator[AsyncSession, None]:
    """Сессия learning-контура: отдельный пул с минимальной DB-ролью (§10.8),
    пока задан LEARNING_DB_PASSWORD; иначе общий движок (dev/тесты)."""
    _notice_learning_engine()
    async for session in _managed_session(LearningSessionLocal):
        yield session
