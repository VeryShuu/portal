"""Integration: агрегаты статистики экскурса (GET /admin/system/settings/onboarding/stats).

Требует INTEGRATION_DB=true и поднятый PostgreSQL с применёнными миграциями.
Каждый тест выполняется внутри SAVEPOINT, откатываемого после теста.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration


def _skip_if_no_db():
    if os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"):
        pytest.skip("INTEGRATION_DB=true required")


@pytest_asyncio.fixture
async def db(real_db_session):
    return real_db_session


async def _create_user(session, *, preferences: dict) -> None:
    from app.models.user import User

    session.add(
        User(
            email=f"onb-stats-{uuid.uuid4().hex[:8]}@portal.local",
            full_name="Onboarding Stats Test",
            role="reader",
            auth_source="local",
            password_hash=None,
            current_status="working",
            notify_email=True,
            notify_inapp=True,
            lang="ru",
            preferences=preferences,
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_stats_counts_completion_kinds_and_seen_steps(db):
    _skip_if_no_db()

    from app.api.system_settings._onboarding import get_onboarding_stats

    class _FakeAdmin:
        pass

    before = await get_onboarding_stats(admin=_FakeAdmin(), db=db)

    # 4 тестовых пользователя: не начинал / дошёл / пропустил / легаси-завершение
    await _create_user(db, preferences={})
    await _create_user(
        db,
        preferences={
            "onboarding_completed": True,
            "onboarding_completed_via": "finished",
            "onboarding_seen_step_ids": ["default-news"],
        },
    )
    await _create_user(
        db,
        preferences={"onboarding_completed": True, "onboarding_completed_via": "skipped"},
    )
    await _create_user(db, preferences={"onboarding_completed": True})
    await db.flush()

    after = await get_onboarding_stats(admin=_FakeAdmin(), db=db)

    assert after.total_users == before.total_users + 4
    assert after.completed == before.completed + 3
    assert after.completed_via_finished == before.completed_via_finished + 1
    assert after.completed_via_skipped == before.completed_via_skipped + 1
    # Легаси-завершение (до внедрения метрики) попадает только в completed
    before_unknown = before.completed - before.completed_via_finished - before.completed_via_skipped
    after_unknown = after.completed - after.completed_via_finished - after.completed_via_skipped
    assert after_unknown == before_unknown + 1

    seen_before = before.seen_step_counts.get("default-news", 0)
    assert after.seen_step_counts.get("default-news", 0) == seen_before + 1


@pytest.mark.asyncio
async def test_stats_empty_seen_step_ids_ignored(db):
    _skip_if_no_db()

    from app.api.system_settings._onboarding import get_onboarding_stats

    class _FakeAdmin:
        pass

    before = await get_onboarding_stats(admin=_FakeAdmin(), db=db)

    # Пользователь с пустым списком просмотров не создаёт мусорных ключей
    await _create_user(
        db, preferences={"onboarding_completed": True, "onboarding_seen_step_ids": []}
    )
    await db.flush()

    after = await get_onboarding_stats(admin=_FakeAdmin(), db=db)
    assert after.total_users == before.total_users + 1
    assert after.completed == before.completed + 1
    assert set(after.seen_step_counts) >= set(before.seen_step_counts)
