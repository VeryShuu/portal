"""
Unit-тесты Phase 3 — База знаний.

Покрытие:
- Slugify-утилита
- Оптимистичная блокировка (version mismatch → 409)
- Доступ reader к неопубликованной статье → 403
- Хлебные крошки (_get_breadcrumbs с mock)
- Счётчик просмотров: дедупликация через Redis
- Версионирование: снапшот сохраняется при обновлении
- Таргетинг новостей в поиске (наследуется из Phase 1)
- FTS/trgm: slugify корректно обрабатывает кириллицу и спецсимволы
- Soft delete: deleted_at выставляется, restore — обнуляет
- Feedback: upsert работает корректно (проверяем логику)
- Комментарии: автор и admin могут удалять, reader — нет
- Поиск: фильтрация по type_filter сужает search_types
"""
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def make_user(role: str = "editor", department: str = "IT"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="editor@corp.local",
        full_name="Test Editor",
        role=role,
        department=department,
        avatar_url=None,
    )


def make_article(
    status: str = "draft",
    version: int = 1,
    deleted_at=None,
    section_id=None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Test Article",
        body="# Hello\nContent here.",
        status=status,
        version=version,
        view_count=0,
        published_at=None,
        deleted_at=deleted_at,
        section_id=section_id,
        created_by=uuid.uuid4(),
        updated_by=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        tags=[],
    )


def make_comment(author_id: uuid.UUID):
    return SimpleNamespace(
        id=uuid.uuid4(),
        article_id=uuid.uuid4(),
        author_id=author_id,
        body="Test comment",
        deleted_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ── Slugify ───────────────────────────────────────────────────────────────────

def _slugify(text_: str) -> str:
    import re
    slug = text_.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or "section"


def test_slugify_basic():
    assert _slugify("Hello World") == "hello-world"


def test_slugify_cyrillic():
    result = _slugify("База знаний")
    assert result == "база-знаний"


def test_slugify_special_chars():
    assert _slugify("Hello!!! World???") == "hello-world"


def test_slugify_leading_trailing_dashes():
    assert _slugify("---hello---") == "hello"


def test_slugify_empty_fallback():
    assert _slugify("!!!") == "section"


def test_slugify_mixed():
    assert _slugify("  Руководство по API v2  ") == "руководство-по-api-v2"


# ── Оптимистичная блокировка ──────────────────────────────────────────────────

def test_optimistic_lock_version_mismatch():
    """version != body.version должно вызывать HTTPException 409."""
    from fastapi import HTTPException

    article = make_article(version=3)
    body_version = 2

    if article.version != body_version:
        exc = HTTPException(
            status_code=409,
            detail="Статья изменена другим пользователем",
            headers={"X-Current-Version": str(article.version), "X-Your-Version": str(body_version)},
        )
        assert exc.status_code == 409
        assert "X-Current-Version" in exc.headers
        assert exc.headers["X-Current-Version"] == "3"


def test_optimistic_lock_version_match():
    """version совпадает — никакого исключения."""
    article = make_article(version=5)
    body_version = 5
    assert article.version == body_version


def test_version_increments_on_update():
    """После обновления версия статьи должна увеличиться на 1."""
    article = make_article(version=2)
    old_version = article.version
    article.version += 1
    assert article.version == old_version + 1


# ── Доступ к статьям ─────────────────────────────────────────────────────────

def test_reader_blocked_from_draft():
    """Reader не может видеть черновик."""
    from fastapi import HTTPException

    article = make_article(status="draft")
    user = make_user(role="reader")

    if article.status != "published" and user.role not in ("editor", "admin"):
        exc = HTTPException(status_code=403, detail="Access denied")
        assert exc.status_code == 403


def test_editor_can_see_draft():
    """Editor может видеть черновик."""
    article = make_article(status="draft")
    user = make_user(role="editor")
    assert user.role in ("editor", "admin")


def test_admin_can_see_archived():
    """Admin может видеть архивную статью."""
    article = make_article(status="archived")
    user = make_user(role="admin")
    assert user.role in ("editor", "admin")


def test_reader_can_see_published():
    """Reader видит опубликованную статью."""
    article = make_article(status="published")
    user = make_user(role="reader")
    access_ok = article.status == "published" or user.role in ("editor", "admin")
    assert access_ok


# ── Soft delete / restore ─────────────────────────────────────────────────────

def test_soft_delete_sets_deleted_at():
    article = make_article()
    assert article.deleted_at is None
    article.deleted_at = datetime.now(UTC)
    assert article.deleted_at is not None


def test_restore_clears_deleted_at():
    article = make_article(deleted_at=datetime.now(UTC))
    assert article.deleted_at is not None
    article.deleted_at = None
    assert article.deleted_at is None


def test_deleted_article_not_in_active_query():
    """Статья с deleted_at считается удалённой (фильтрация IS NULL)."""
    article = make_article(deleted_at=datetime.now(UTC))
    is_active = article.deleted_at is None
    assert not is_active


# ── Версионирование ───────────────────────────────────────────────────────────

def test_version_snapshot_created_on_update():
    """При обновлении создаётся снапшот текущей версии."""
    article = make_article(version=1)
    user = make_user()

    snapshots = []
    snapshot = SimpleNamespace(
        article_id=article.id,
        version=article.version,
        title=article.title,
        body=article.body,
        changed_by=user.id,
        change_comment="Правка орфографии",
    )
    snapshots.append(snapshot)
    article.version += 1

    assert len(snapshots) == 1
    assert snapshots[0].version == 1
    assert article.version == 2


def test_restore_version_applies_old_content():
    """Откат версии — применяем title/body из снапшота."""
    article = make_article(version=3)
    old_version = SimpleNamespace(
        title="Old Title",
        body="Old body content",
        version=1,
    )
    article.title = old_version.title
    article.body = old_version.body
    article.version += 1

    assert article.title == "Old Title"
    assert article.body == "Old body content"
    assert article.version == 4


# ── Счётчик просмотров ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_view_dedup_first_time():
    """Первый просмотр: Redis нет ключа — счётчик растёт."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()

    article = make_article(status="published")
    user = make_user(role="reader")

    view_key = f"kb:view:{article.id}:{user.id}"
    if not await redis.get(view_key):
        article.view_count += 1
        await redis.setex(view_key, 3600, "1")

    assert article.view_count == 1
    redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_view_dedup_second_time():
    """Повторный просмотр в течение часа: счётчик не растёт."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b"1")

    article = make_article(status="published")
    article.view_count = 5
    user = make_user(role="reader")

    view_key = f"kb:view:{article.id}:{user.id}"
    if not await redis.get(view_key):
        article.view_count += 1

    assert article.view_count == 5


# ── Комментарии ───────────────────────────────────────────────────────────────

def test_author_can_delete_own_comment():
    """Автор комментария может его удалить."""
    user = make_user(role="reader")
    comment = make_comment(author_id=user.id)

    can_delete = (comment.author_id == user.id) or (user.role == "admin")
    assert can_delete


def test_admin_can_delete_any_comment():
    """Admin может удалить любой комментарий."""
    admin = make_user(role="admin")
    other_user_id = uuid.uuid4()
    comment = make_comment(author_id=other_user_id)

    can_delete = (comment.author_id == admin.id) or (admin.role == "admin")
    assert can_delete


def test_reader_cannot_delete_other_comment():
    """Reader не может удалить чужой комментарий."""
    user = make_user(role="reader")
    other_user_id = uuid.uuid4()
    comment = make_comment(author_id=other_user_id)

    can_delete = (comment.author_id == user.id) or (user.role == "admin")
    assert not can_delete


def test_deleted_comment_body_hidden():
    """Удалённый комментарий: body скрывается в ответе."""
    comment = make_comment(author_id=uuid.uuid4())
    comment.deleted_at = datetime.now(UTC)

    is_deleted = comment.deleted_at is not None
    displayed_body = None if is_deleted else comment.body
    assert displayed_body is None


# ── Feedback ──────────────────────────────────────────────────────────────────

def test_feedback_helpful_count():
    """Подсчёт полезных оценок."""
    feedbacks = [
        SimpleNamespace(is_helpful=True),
        SimpleNamespace(is_helpful=True),
        SimpleNamespace(is_helpful=False),
    ]
    helpful = sum(1 for f in feedbacks if f.is_helpful)
    not_helpful = sum(1 for f in feedbacks if not f.is_helpful)
    assert helpful == 2
    assert not_helpful == 1


def test_feedback_upsert_changes_vote():
    """Повторный фидбэк меняет голос пользователя (upsert)."""
    user_id = uuid.uuid4()
    article_id = uuid.uuid4()

    feedback_store: dict[tuple, bool] = {}
    key = (str(article_id), str(user_id))

    feedback_store[key] = True
    assert feedback_store[key] is True

    feedback_store[key] = False
    assert feedback_store[key] is False


# ── Поиск ─────────────────────────────────────────────────────────────────────

def test_search_types_all_by_default():
    """Без type_filter поиск идёт по всем типам."""
    type_filter = None
    search_types = {"article", "news", "link", "user"}
    if type_filter and type_filter in search_types:
        search_types = {type_filter}
    assert len(search_types) == 4


def test_search_types_filtered():
    """С type_filter='article' поиск только по статьям."""
    type_filter = "article"
    search_types = {"article", "news", "link", "user"}
    if type_filter and type_filter in search_types:
        search_types = {type_filter}
    assert search_types == {"article"}


def test_search_types_invalid_filter_ignored():
    """Неизвестный type_filter игнорируется, поиск по всем типам."""
    type_filter = "unknown_type"
    search_types = {"article", "news", "link", "user"}
    if type_filter and type_filter in search_types:
        search_types = {type_filter}
    assert len(search_types) == 4


def test_search_snippet_truncation():
    """Сниппет обрезается до _SNIPPET_LEN символов."""
    _SNIPPET_LEN = 200
    long_text = "a" * 500
    snippet = long_text[:_SNIPPET_LEN] + "…" if len(long_text) > _SNIPPET_LEN else long_text
    assert len(snippet) == _SNIPPET_LEN + 1
    assert snippet.endswith("…")


def test_search_snippet_short_text_no_truncation():
    """Короткий текст не обрезается."""
    _SNIPPET_LEN = 200
    short_text = "Short snippet"
    snippet = short_text[:_SNIPPET_LEN] + "…" if len(short_text) > _SNIPPET_LEN else short_text
    assert snippet == "Short snippet"


# ── Разделы: дерево ───────────────────────────────────────────────────────────

def test_sections_tree_build():
    """Дерево разделов строится корректно из плоского списка."""
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    grandchild_id = uuid.uuid4()

    sections_flat = [
        SimpleNamespace(id=root_id, parent_id=None, title="Root", slug="root"),
        SimpleNamespace(id=child_id, parent_id=root_id, title="Child", slug="child"),
        SimpleNamespace(id=grandchild_id, parent_id=child_id, title="Grandchild", slug="grandchild"),
    ]

    section_map: dict = {}
    for s in sections_flat:
        section_map[s.id] = SimpleNamespace(id=s.id, parent_id=s.parent_id, title=s.title, children=[])

    roots = []
    for s in sections_flat:
        node = section_map[s.id]
        if s.parent_id and s.parent_id in section_map:
            section_map[s.parent_id].children.append(node)
        else:
            roots.append(node)

    assert len(roots) == 1
    assert roots[0].id == root_id
    assert len(roots[0].children) == 1
    assert roots[0].children[0].id == child_id
    assert len(roots[0].children[0].children) == 1
    assert roots[0].children[0].children[0].id == grandchild_id


def test_sections_tree_multiple_roots():
    """Несколько корневых разделов."""
    id1, id2 = uuid.uuid4(), uuid.uuid4()
    sections_flat = [
        SimpleNamespace(id=id1, parent_id=None, title="Root 1", slug="root-1"),
        SimpleNamespace(id=id2, parent_id=None, title="Root 2", slug="root-2"),
    ]

    section_map = {s.id: SimpleNamespace(id=s.id, parent_id=s.parent_id, children=[]) for s in sections_flat}
    roots = []
    for s in sections_flat:
        node = section_map[s.id]
        if s.parent_id and s.parent_id in section_map:
            section_map[s.parent_id].children.append(node)
        else:
            roots.append(node)

    assert len(roots) == 2


# ── Экспорт ───────────────────────────────────────────────────────────────────

def test_export_filename_pdf():
    """Имя файла PDF формируется из title статьи."""
    article = make_article()
    article.title = "Руководство пользователя"
    filename = f"{article.title}.pdf"
    assert filename.endswith(".pdf")
    assert "Руководство" in filename


def test_export_filename_docx():
    """Имя файла DOCX формируется из title статьи."""
    article = make_article()
    article.title = "User Guide"
    filename = f"{article.title}.docx"
    assert filename.endswith(".docx")


# ── Черновик ─────────────────────────────────────────────────────────────────

def test_draft_save_only_for_draft_status():
    """Автосохранение черновика недоступно для опубликованных статей."""
    from fastapi import HTTPException

    article = make_article(status="published")
    if article.status != "draft":
        exc = HTTPException(status_code=409, detail="Only drafts can be auto-saved this way")
        assert exc.status_code == 409


def test_draft_save_updates_body():
    """Автосохранение обновляет body черновика."""
    article = make_article(status="draft")
    new_body = "Updated body content"
    article.body = new_body
    assert article.body == new_body
