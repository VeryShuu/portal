"""Integration: News service против реальной PostgreSQL.

Покрывает:
- create_news → запись + первая версия + sanitize HTML
- update_news → инкремент current_version + новая запись в news_versions
- delete_news → soft delete (deleted_at заполнен, status = archived)
- Таргетинг по department/role работает на уровне SQL (ARRAY contains)
- pinned_first сортировка
- FTS body_tsvector заполняется триггером (generated column из миграции 002/007)
- Версионирование сохраняет историю
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.news import News, NewsVersion
from app.services.news import (
    create_news,
    delete_news,
    get_news_list,
    update_news,
)


pytestmark = pytest.mark.asyncio


async def test_create_news_persists_and_creates_first_version(real_db_session, real_editor):
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={
            "title": "Hello world",
            "body": "<p>Body</p>",
            "status": "published",
        },
    )
    assert news.id is not None
    assert news.current_version == 1

    versions = (
        await real_db_session.execute(
            select(NewsVersion).where(NewsVersion.news_id == news.id)
        )
    ).scalars().all()
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].title == "Hello world"


async def test_create_news_sanitizes_xss(real_db_session, real_editor):
    """XSS-вектор должен быть вычищен bleach до записи в БД."""
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={
            "title": "Evil",
            "body": "<p>safe</p><script>alert(1)</script><img src=x onerror=alert(1)>",
            "status": "published",
        },
    )
    assert "<script>" not in news.body
    assert "onerror" not in news.body
    assert "<p>safe</p>" in news.body


async def test_update_news_increments_version(real_db_session, real_editor):
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "v1", "body": "<p>v1</p>", "status": "draft"},
    )
    assert news.current_version == 1

    updated = await update_news(
        real_db_session,
        news=news,
        editor=real_editor,
        data={"title": "v2"},
    )
    assert updated.current_version == 2

    versions = (
        await real_db_session.execute(
            select(NewsVersion).where(NewsVersion.news_id == news.id).order_by(NewsVersion.version)
        )
    ).scalars().all()
    assert [v.version for v in versions] == [1, 2]
    assert versions[1].title == "v2"


async def test_update_news_no_changes_no_version(real_db_session, real_editor):
    """Если значения не изменились — новая версия не создаётся."""
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "stable", "body": "<p>x</p>", "status": "draft"},
    )
    await update_news(
        real_db_session,
        news=news,
        editor=real_editor,
        data={"title": "stable"},  # тот же
    )
    assert news.current_version == 1


async def test_delete_news_soft(real_db_session, real_editor):
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "To delete", "body": "<p>x</p>", "status": "published"},
    )
    await delete_news(real_db_session, news)
    assert news.deleted_at is not None
    assert news.status == "archived"

    # not visible in active listing
    items, total = await get_news_list(
        real_db_session, user=real_editor, page=1, page_size=50
    )
    assert all(n.id != news.id for n in items)


async def test_targeting_by_department(real_db_session, real_editor, real_user):
    """real_user.department='IT', news для department='HR' → не виден."""
    await create_news(
        real_db_session,
        author=real_editor,
        data={
            "title": "HR only",
            "body": "<p>x</p>",
            "status": "published",
            "target_departments": ["HR"],
        },
    )
    await create_news(
        real_db_session,
        author=real_editor,
        data={
            "title": "IT only",
            "body": "<p>x</p>",
            "status": "published",
            "target_departments": ["IT"],
        },
    )
    items, total = await get_news_list(
        real_db_session, user=real_user, page=1, page_size=50
    )
    titles = {n.title for n in items}
    assert "IT only" in titles
    assert "HR only" not in titles


async def test_targeting_by_role(real_db_session, real_editor, real_user):
    """user.role='reader', news для editor → не виден."""
    await create_news(
        real_db_session,
        author=real_editor,
        data={
            "title": "Editors only",
            "body": "<p>x</p>",
            "status": "published",
            "target_roles": ["editor", "admin"],
        },
    )
    items, _ = await get_news_list(
        real_db_session, user=real_user, page=1, page_size=50
    )
    assert all(n.title != "Editors only" for n in items)


async def test_pinned_first_ordering(real_db_session, real_editor):
    older = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Old", "body": "<p>x</p>", "status": "published"},
    )
    older.published_at = datetime.now(UTC) - timedelta(days=2)
    pinned = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Pin", "body": "<p>x</p>", "status": "published", "is_pinned": True},
    )
    pinned.published_at = datetime.now(UTC) - timedelta(days=5)  # старше, но pinned
    await real_db_session.commit()

    items, _ = await get_news_list(
        real_db_session, user=real_editor, page=1, page_size=50, pinned_first=True
    )
    assert items[0].title == "Pin"


async def test_news_fts_tsvector_populated(real_db_session, real_editor):
    """Сгенерированная колонка body_tsvector должна заполняться автоматически."""
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={
            "title": "Тестовая новость",
            "body": "<p>Платежи и зарплата сотрудников</p>",
            "status": "published",
        },
    )
    refreshed = (
        await real_db_session.execute(select(News).where(News.id == news.id))
    ).scalar_one()
    assert refreshed.body_tsvector is not None
    # Должны присутствовать какие-то токены (может быть кириллица — главное не пусто)
    assert len(str(refreshed.body_tsvector)) > 0
