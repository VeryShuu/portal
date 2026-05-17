"""Integration test: concurrent bookmark creation must not exceed MAX_BOOKMARKS_PER_USER.

Uses real PostgreSQL (INTEGRATION_DB=true required).  Verifies that the
pg_advisory_xact_lock in create_bookmark serializes concurrent inserts and the
limit of 100 bookmarks per user is never exceeded.
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
                    (id, email, full_name, role, auth_source, presence_status,
                     notify_email, notify_inapp, lang, preferences, updated_at)
                VALUES
                    (:id, :email, 'Race Test User', 'reader', 'local', 'office',
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


async def _insert_bookmark(engine, user_id: uuid.UUID, title: str) -> None:
    """Insert one bookmark using a fresh independent session (commits for real)."""
    import hashlib

    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api.bookmarks import _BOOKMARK_LOCK_NAMESPACE, MAX_BOOKMARKS_PER_USER
    from app.models.links import Bookmark

    user_lock_key = int.from_bytes(hashlib.sha256(user_id.bytes).digest()[:4], "big", signed=True)

    async with AsyncSession(engine, expire_on_commit=False) as s, s.begin():
        await s.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :k)"),
            {"ns": _BOOKMARK_LOCK_NAMESPACE, "k": user_lock_key},
        )
        count_result = await s.execute(
            select(func.count()).select_from(Bookmark).where(Bookmark.user_id == user_id)
        )
        count = count_result.scalar_one()
        if count >= MAX_BOOKMARKS_PER_USER:
            return

        max_order = await s.execute(
            select(func.coalesce(func.max(Bookmark.sort_order), 0)).where(
                Bookmark.user_id == user_id
            )
        )
        next_order = max_order.scalar_one() + 1

        bm = Bookmark(
            user_id=user_id,
            title=title,
            url="https://example.local/page",
            resource_type="link",
            sort_order=next_order,
        )
        s.add(bm)


async def test_concurrent_bookmark_creation_respects_limit(_engine, _user_id):
    """Five concurrent tasks race to create bookmarks; none should exceed the limit."""
    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api.bookmarks import MAX_BOOKMARKS_PER_USER
    from app.models.links import Bookmark

    pre_fill_count = MAX_BOOKMARKS_PER_USER - 2

    from sqlalchemy import insert as sa_insert

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

    tasks = [_insert_bookmark(_engine, _user_id, f"Race bookmark {i}") for i in range(5)]
    await asyncio.gather(*tasks, return_exceptions=True)

    async with AsyncSession(_engine, expire_on_commit=False) as s:
        result = await s.execute(
            select(func.count()).select_from(Bookmark).where(Bookmark.user_id == _user_id)
        )
        final_count = result.scalar_one()

    assert final_count <= MAX_BOOKMARKS_PER_USER, (
        f"Bookmark count {final_count} exceeded MAX_BOOKMARKS_PER_USER={MAX_BOOKMARKS_PER_USER}"
    )
    assert final_count == MAX_BOOKMARKS_PER_USER, (
        f"Expected exactly {MAX_BOOKMARKS_PER_USER} bookmarks, got {final_count}"
    )
