"""Integration tests for analytics endpoints with a real PostgreSQL database.

Requires INTEGRATION_DB=true and a running PostgreSQL with migrations applied.
Each test runs inside a SAVEPOINT that is rolled back after the test.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration


def _skip_if_no_db():
    if os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"):
        pytest.skip("INTEGRATION_DB=true required")


@pytest_asyncio.fixture
async def db(real_db_session):
    return real_db_session


@pytest.mark.asyncio
async def test_analytics_dashboard_structure(db):
    """Dashboard endpoint возвращает ожидаемую структуру без ошибок."""
    _skip_if_no_db()

    from app.api.analytics import get_dashboard

    class _FakeAdmin:
        pass

    result = await get_dashboard(_admin=_FakeAdmin(), db=db)

    assert "users" in result
    assert "content" in result
    assert "activity" in result
    assert "series" in result

    assert "total" in result["users"]
    assert "active_30d" in result["users"]
    assert "new_30d" in result["users"]
    assert "active_1h" in result["users"]

    assert "news_published_30d" in result["content"]
    assert "kb_articles_published_30d" in result["content"]

    assert "audit_events_24h" in result["activity"]
    assert "logins_24h" in result["activity"]

    assert "daily_logins_14d" in result["series"]
    assert "daily_publications_14d" in result["series"]


@pytest.mark.asyncio
async def test_analytics_counts_reflect_seeded_users(db):
    """total_users включает пользователей, созданных в тесте."""
    _skip_if_no_db()

    from sqlalchemy import text

    from app.api.analytics import get_dashboard

    class _FakeAdmin:
        pass

    baseline = await get_dashboard(_admin=_FakeAdmin(), db=db)
    baseline_total = baseline["users"]["total"]

    new_email = f"analytics-test-{uuid.uuid4().hex[:8]}@test.local"
    await db.execute(
        text(
            """
            INSERT INTO users
                (id, email, full_name, auth_source, role, presence_status,
                 notify_email, notify_inapp, lang, preferences, keycloak_groups,
                 attributes, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :email, 'Analytics Test User',
                 'local', 'reader', 'office', true, true, 'ru',
                 '{}'::jsonb, '{}'::text[], '{}'::jsonb, NOW(), NOW())
            """
        ),
        {"email": new_email},
    )
    await db.flush()

    result = await get_dashboard(_admin=_FakeAdmin(), db=db)
    assert result["users"]["total"] == baseline_total + 1


@pytest.mark.asyncio
async def test_analytics_new_users_30d(db):
    """new_users_30d учитывает пользователей, созданных в течение 30 дней."""
    _skip_if_no_db()

    from sqlalchemy import text

    from app.api.analytics import get_dashboard

    class _FakeAdmin:
        pass

    baseline = await get_dashboard(_admin=_FakeAdmin(), db=db)
    baseline_new = baseline["users"]["new_30d"]

    new_email = f"new-user-{uuid.uuid4().hex[:8]}@test.local"
    await db.execute(
        text(
            """
            INSERT INTO users
                (id, email, full_name, auth_source, role, presence_status,
                 notify_email, notify_inapp, lang, preferences, keycloak_groups,
                 attributes, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :email, 'New User 30d',
                 'local', 'reader', 'office', true, true, 'ru',
                 '{}'::jsonb, '{}'::text[], '{}'::jsonb,
                 NOW() - INTERVAL '10 days', NOW())
            """
        ),
        {"email": new_email},
    )

    old_email = f"old-user-{uuid.uuid4().hex[:8]}@test.local"
    await db.execute(
        text(
            """
            INSERT INTO users
                (id, email, full_name, auth_source, role, presence_status,
                 notify_email, notify_inapp, lang, preferences, keycloak_groups,
                 attributes, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :email, 'Old User 60d',
                 'local', 'reader', 'office', true, true, 'ru',
                 '{}'::jsonb, '{}'::text[], '{}'::jsonb,
                 NOW() - INTERVAL '60 days', NOW())
            """
        ),
        {"email": old_email},
    )
    await db.flush()

    result = await get_dashboard(_admin=_FakeAdmin(), db=db)
    assert result["users"]["new_30d"] == baseline_new + 1, (
        "Only the user created within 30 days should count"
    )


@pytest.mark.asyncio
async def test_analytics_counts_non_negative(db):
    """Все числовые агрегаты должны быть >= 0."""
    _skip_if_no_db()

    from app.api.analytics import get_dashboard

    class _FakeAdmin:
        pass

    result = await get_dashboard(_admin=_FakeAdmin(), db=db)

    assert result["users"]["total"] >= 0
    assert result["users"]["active_30d"] >= 0
    assert result["users"]["new_30d"] >= 0
    assert result["users"]["active_1h"] >= 0
    assert result["content"]["news_published_30d"] >= 0
    assert result["content"]["kb_articles_published_30d"] >= 0
    assert result["activity"]["audit_events_24h"] >= 0
    assert result["activity"]["logins_24h"] >= 0
    assert isinstance(result["series"]["daily_logins_14d"], list)
    assert isinstance(result["series"]["daily_publications_14d"], list)
