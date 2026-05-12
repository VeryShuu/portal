"""Integration: News service против реальной PostgreSQL.

Покрывает:
- create_news → запись + первая версия + sanitize HTML
- update_news → инкремент current_version + новая запись в news_versions
- delete_news → soft delete (deleted_at заполнен, status = archived, previous_status сохранён)
- restore_news → статус возвращается из previous_status, deleted_at/previous_status обнуляются
- purge_news → удаляет файлы, строку news, каскад на связанные таблицы, bookmarks
- get_trash_news → возвращает только soft-удалённые
- Таргетинг по department/role работает на уровне SQL (ARRAY contains)
- pinned_first сортировка
- FTS body_tsvector заполняется триггером (generated column из миграции 002/007)
- Версионирование сохраняет историю
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.models.links import Bookmark
from app.models.news import News, NewsVersion
from app.services.news import (
    create_news,
    delete_news,
    get_news_list,
    get_trash_news,
    purge_news,
    restore_news,
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
        (await real_db_session.execute(select(NewsVersion).where(NewsVersion.news_id == news.id)))
        .scalars()
        .all()
    )
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
        (
            await real_db_session.execute(
                select(NewsVersion)
                .where(NewsVersion.news_id == news.id)
                .order_by(NewsVersion.version)
            )
        )
        .scalars()
        .all()
    )
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
    items, total = await get_news_list(real_db_session, user=real_editor, page=1, page_size=50)
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
    items, total = await get_news_list(real_db_session, user=real_user, page=1, page_size=50)
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
    items, _ = await get_news_list(real_db_session, user=real_user, page=1, page_size=50)
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
    refreshed = (await real_db_session.execute(select(News).where(News.id == news.id))).scalar_one()
    assert refreshed.body_tsvector is not None
    # Должны присутствовать какие-то токены (может быть кириллица — главное не пусто)
    assert len(str(refreshed.body_tsvector)) > 0


# ── Корзина: delete / restore / purge / get_trash_news ───────────────────────


async def test_delete_news_saves_previous_status(real_db_session, real_editor):
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "To trash", "body": "<p>x</p>", "status": "published"},
    )
    await delete_news(real_db_session, news)
    assert news.previous_status == "published"
    assert news.deleted_at is not None
    assert news.status == "archived"


async def test_delete_news_saves_previous_status_draft(real_db_session, real_editor):
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Draft trash", "body": "<p>x</p>", "status": "draft"},
    )
    await delete_news(real_db_session, news)
    assert news.previous_status == "draft"
    assert news.status == "archived"


async def test_restore_news_restores_status_from_previous(real_db_session, real_editor):
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Restore me", "body": "<p>x</p>", "status": "published"},
    )
    await delete_news(real_db_session, news)
    assert news.previous_status == "published"

    restored = await restore_news(real_db_session, news)
    assert restored.deleted_at is None
    assert restored.status == "published"
    assert restored.previous_status is None


async def test_restore_news_no_previous_status_keeps_current(real_db_session, real_editor):
    """Старые записи без previous_status: статус не меняется при восстановлении."""
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Old record", "body": "<p>x</p>", "status": "archived"},
    )
    news.deleted_at = datetime.now(UTC)
    news.previous_status = None
    await real_db_session.commit()
    await real_db_session.refresh(news)

    restored = await restore_news(real_db_session, news)
    assert restored.deleted_at is None
    assert restored.status == "archived"
    assert restored.previous_status is None


async def test_get_trash_news_returns_only_deleted(real_db_session, real_editor):
    active = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Active", "body": "<p>x</p>", "status": "published"},
    )
    trashed = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Trashed", "body": "<p>x</p>", "status": "draft"},
    )
    await delete_news(real_db_session, trashed)

    items, total = await get_trash_news(real_db_session, page=1, page_size=50)
    trash_ids = {n.id for n in items}
    assert trashed.id in trash_ids
    assert active.id not in trash_ids
    assert total >= 1

    # author должен быть eager-loaded (selectinload), иначе /news/trash
    # упадёт с MissingGreenlet при сериализации NewsWithAuthor.
    trashed_item = next(n for n in items if n.id == trashed.id)
    from sqlalchemy import inspect as _sa_inspect
    assert "author" not in _sa_inspect(trashed_item).unloaded
    assert trashed_item.author is not None
    assert trashed_item.author.id == real_editor.id


async def test_purge_news_deletes_db_row(real_db_session, real_editor):
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Purge me", "body": "<p>x</p>", "status": "draft"},
    )
    news_id = news.id
    await delete_news(real_db_session, news)
    await purge_news(real_db_session, news)

    result = await real_db_session.execute(select(News).where(News.id == news_id))
    assert result.scalar_one_or_none() is None


async def test_purge_news_cleans_bookmarks(real_db_session, real_editor, real_user):
    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Bookmarked", "body": "<p>x</p>", "status": "published"},
    )
    bookmark = Bookmark(
        user_id=real_user.id,
        resource_type="news",
        resource_id=str(news.id),
        title="Test bookmark",
        sort_order=0,
    )
    real_db_session.add(bookmark)
    await real_db_session.commit()

    await delete_news(real_db_session, news)
    await purge_news(real_db_session, news)

    remaining = (
        await real_db_session.execute(
            select(Bookmark).where(
                Bookmark.resource_type == "news",
                Bookmark.resource_id == str(news.id),
            )
        )
    ).scalars().all()
    assert len(remaining) == 0


async def test_purge_news_removes_media_directory(real_db_session, real_editor, tmp_path, monkeypatch):
    import app.services.news as news_module

    monkeypatch.setattr(news_module, "_NEWS_MEDIA_DIR", tmp_path)

    news = await create_news(
        real_db_session,
        author=real_editor,
        data={"title": "Has media", "body": "<p>x</p>", "status": "draft"},
    )
    news_dir = tmp_path / str(news.id)
    news_dir.mkdir()
    (news_dir / "cover.jpg").write_text("fake")

    await delete_news(real_db_session, news)
    await purge_news(real_db_session, news)

    assert not news_dir.exists()
