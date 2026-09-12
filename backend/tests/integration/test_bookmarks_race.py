"""Integration test: concurrent bookmark creation must not exceed MAX_BOOKMARKS_PER_USER.

Uses real PostgreSQL (INTEGRATION_DB=true required). Verifies that the
pg_advisory_xact_lock inside the PRODUCTION create_bookmark router serializes
concurrent inserts and the limit of 100 bookmarks per user is never exceeded.

Аудит тестирования 2026-08-23 (P1): прежняя версия тестировала собственную
копию алгоритма (lock/count/order/insert дублировались в тесте, из
production импортировались только константы) — удаление acquire_user_lock
из роутера не роняло тест. Теперь конкурентные вызовы идут через
app.api.bookmarks.create_bookmark (паттерн «роутер и тест зовут одну
функцию», как helpdesk.take_ticket_tx / files.revoke_share).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


def _skip_if_no_db():
    if os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"):
        pytest.skip("INTEGRATION_DB=true required")


@pytest_asyncio.fixture
async def _engine():
    _skip_if_no_db()

    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=10)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def _user_id(_engine):
    """Create a real user row; yield its UUID; clean up afterwards."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    uid = uuid.uuid4()
    async with AsyncSession(_engine, expire_on_commit=False) as s:
        await s.execute(
            text(
                """
                INSERT INTO users
                    (id, email, full_name, role, auth_source,
                     notify_email, notify_inapp, lang, preferences, updated_at)
                VALUES
                    (:id, :email, 'Race Test User', 'reader', 'local',
                     true, true, 'ru', '{}', :now)
                """
            ),
            {"id": uid, "email": f"race-{uid.hex[:8]}@test.local", "now": datetime.now(UTC)},
        )
        await s.commit()

    yield uid

    async with AsyncSession(_engine, expire_on_commit=False) as s:
        await s.execute(text("DELETE FROM bookmarks WHERE user_id = :uid"), {"uid": uid})
        await s.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
        await s.commit()


async def _create_via_router(engine, user_id: uuid.UUID, title: str):
    """Одна конкурентная вставка ЧЕРЕЗ production-роутер create_bookmark.

    Роутер использует только ``user.id``, поэтому хватает detached-объекта
    User (без БД-сессии); сессия запроса независимая, с реальным commit —
    как отдельный HTTP-вызов.
    """
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api.bookmarks import create_bookmark
    from app.models.user import User
    from app.schemas.links import CreateBookmarkRequest

    body = CreateBookmarkRequest(title=title, url="https://example.local/page")
    user = User(id=user_id)

    async with AsyncSession(engine, expire_on_commit=False) as db:
        try:
            bookmark = await create_bookmark(body=body, user=user, db=db)
            return ("created", bookmark.sort_order)
        except HTTPException as exc:
            return ("rejected", exc.status_code)


async def test_concurrent_bookmark_creation_respects_limit(_engine, _user_id, monkeypatch):
    """Five concurrent router calls race; the limit must hold exactly.

    Review-2 (P2): детерминированный spy вокруг production acquire_user_lock —
    каждый конкурентный вызов роутера обязан взять advisory lock (спай вызывает
    настоящую функцию). Удаление acquire_user_lock из роутера теперь ловится
    счётчиком гарантированно, а не только вероятностным нарушением лимита.
    """
    from sqlalchemy import func, select
    from sqlalchemy import insert as sa_insert
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api import bookmarks_repo
    from app.api.bookmarks import MAX_BOOKMARKS_PER_USER
    from app.models.links import Bookmark

    lock_calls = {"count": 0}
    original_lock = bookmarks_repo.acquire_user_lock

    async def _spy_lock(db, *, namespace: int, key: int):
        lock_calls["count"] += 1
        return await original_lock(db, namespace=namespace, key=key)

    # роутер зовёт bookmarks_repo.acquire_user_lock(...) — патчим атрибут
    # модуля-репозитория; спай вызывает НАСТОЯЩУЮ функцию (не тестовую копию)
    monkeypatch.setattr(bookmarks_repo, "acquire_user_lock", _spy_lock)

    pre_fill_count = MAX_BOOKMARKS_PER_USER - 2

    async with AsyncSession(_engine, expire_on_commit=False) as s, s.begin():
        rows = [
            {
                "id": uuid.uuid4(),
                "user_id": _user_id,
                "title": f"Pre-fill {i}",
                "url": "https://example.local",
                "resource_type": "link",
                "sort_order": i,
            }
            for i in range(pre_fill_count)
        ]
        await s.execute(sa_insert(Bookmark), rows)

    results = await asyncio.gather(
        *(_create_via_router(_engine, _user_id, f"Race bookmark {i}") for i in range(5))
    )

    created = [r for r in results if r[0] == "created"]
    rejected = [r for r in results if r[0] == "rejected"]

    assert len(created) == 2, (
        f"При pre-fill {pre_fill_count}/{MAX_BOOKMARKS_PER_USER} ровно 2 конкурентных "
        f"вызова роутера обязаны пройти, прошло: {len(created)} (results={results})"
    )
    assert len(rejected) == 3
    assert all(status == 422 for _, status in rejected), (
        f"Отклонённые вызовы обязаны получать 422 (limit), получено: {rejected}"
    )

    async with AsyncSession(_engine, expire_on_commit=False) as s:
        final_count = (
            await s.execute(
                select(func.count()).select_from(Bookmark).where(Bookmark.user_id == _user_id)
            )
        ).scalar_one()

    assert final_count == MAX_BOOKMARKS_PER_USER, (
        f"Expected exactly {MAX_BOOKMARKS_PER_USER} bookmarks, got {final_count}"
    )

    # Сериализация через advisory lock гарантирует и монотонные неповторяющиеся
    # sort_order у победивших вставок (без локов возможны дубликаты порядка).
    # pre-fill занимает 0..MAX-3, победившие — MAX-2 и MAX-1.
    orders = sorted(order for _, order in created)
    assert orders == [MAX_BOOKMARKS_PER_USER - 2, MAX_BOOKMARKS_PER_USER - 1], (
        f"sort_order победивших вставок должен быть монотонным: {orders}"
    )

    # Review-2 (P2): детерминированное доказательство, что production-роутер
    # берёт advisory lock на КАЖДОМ конкурентном вызове — удаление
    # acquire_user_lock из create_bookmark роняет тест сразу, а не при
    # невезучей раскладке гонки.
    assert lock_calls["count"] == 5, (
        f"acquire_user_lock вызван {lock_calls['count']} раз вместо 5 — "
        "production-роутер перестал сериализовать создание закладок"
    )


async def test_acquire_user_lock_actually_serializes(_engine):
    """Review-3 (P2): spy ловил удаление ВЫЗОВА acquire_user_lock, но no-op
    тело ловилось только вероятностной гонкой. Здесь — детерминированная
    проверка самой production-функции: пока первая транзакция держит
    advisory lock, вторая ОБЯЗАНА блокироваться (факт подтверждается из
    pg_stat_activity по PID), а после commit — проходить. No-op тело
    (пустой SELECT/без lock) падает на барьере «не встала в ожидание».
    """
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api import bookmarks_repo as repo
    from app.api.bookmarks import _BOOKMARK_LOCK_NAMESPACE

    key = 424242  # тестовый ключ вне хэша user_id — изолирован namespace'ом

    async with AsyncSession(_engine, expire_on_commit=False) as holder:
        await repo.acquire_user_lock(holder, namespace=_BOOKMARK_LOCK_NAMESPACE, key=key)

        waiter = AsyncSession(_engine, expire_on_commit=False)
        pid_waiter = (await waiter.execute(text("SELECT pg_backend_pid()"))).scalar_one()

        async def _second():
            await repo.acquire_user_lock(waiter, namespace=_BOOKMARK_LOCK_NAMESPACE, key=key)

        task = asyncio.create_task(_second())

        # барьер: вторая транзакция обязана ВСТАТЬ в ожидание heavyweight-лока
        deadline = asyncio.get_running_loop().time() + 10
        seen_waiting = False
        async with AsyncSession(_engine, expire_on_commit=False) as poll:
            while asyncio.get_running_loop().time() < deadline:
                state = (
                    await poll.execute(
                        text(
                            "SELECT wait_event_type FROM pg_stat_activity "
                            "WHERE pid = :pid AND state = 'active'"
                        ),
                        {"pid": pid_waiter},
                    )
                ).scalar_one_or_none()
                await poll.rollback()
                if state == "Lock":
                    seen_waiting = True
                    break
                await asyncio.sleep(0.05)
        assert seen_waiting, (
            "вторая транзакция не заблокировалась на acquire_user_lock — "
            "тело функции перестало брать advisory lock (no-op)"
        )

        await holder.commit()  # снимает pg_advisory_xact_lock
        await asyncio.wait_for(task, timeout=5)
        await waiter.rollback()
        await waiter.close()
