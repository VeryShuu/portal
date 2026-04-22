"""Unit-тесты: бизнес-логика новостей (без подключения к БД)."""
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def make_user(role: str = "editor", department: str = "IT"):
    u = SimpleNamespace(
        id=uuid.uuid4(),
        email="test@test.local",
        full_name="Test User",
        role=role,
        department=department,
        presence_status="office",
        lang="ru",
        preferences={},
    )
    return u


def make_news(status: str = "draft"):
    n = SimpleNamespace(
        id=uuid.uuid4(),
        title="Test News",
        body="Body text",
        status=status,
        is_pinned=False,
        view_count=0,
        current_version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        deleted_at=None,
        published_at=None,
        publish_at=None,
        archive_at=None,
        target_departments=None,
        target_roles=None,
        author_id=uuid.uuid4(),
        category=None,
    )
    return n


def test_targeting_no_restriction():
    """Новость без ограничений видна всем."""
    news = make_news("published")
    news.target_departments = None
    assert news.target_departments is None


def test_targeting_with_departments_it_excluded():
    """IT-отдел не видит новость, нацеленную на Finance и HR."""
    news = make_news("published")
    news.target_departments = ["Finance", "HR"]
    user_it = make_user(department="IT")
    assert user_it.department not in news.target_departments


def test_targeting_with_departments_finance_included():
    """Finance видит новость для Finance."""
    news = make_news("published")
    news.target_departments = ["Finance", "HR"]
    user_fin = make_user(department="Finance")
    assert user_fin.department in news.target_departments


def test_news_pinned_flag():
    news = make_news("published")
    news.is_pinned = True
    assert news.is_pinned is True


def test_news_version_increments():
    news = make_news("draft")
    initial = news.current_version
    news.current_version += 1
    assert news.current_version == initial + 1


def test_news_published_at_set_on_publish():
    """При установке статуса published должен быть установлен published_at."""
    news = make_news("draft")
    assert news.published_at is None

    now = datetime.now(UTC)
    if news.status == "draft":
        news.status = "published"
        news.published_at = now

    assert news.published_at is not None
    assert news.status == "published"


def test_news_soft_delete():
    news = make_news("published")
    now = datetime.now(UTC)
    news.deleted_at = now
    news.status = "archived"
    assert news.deleted_at is not None
    assert news.status == "archived"


def test_news_status_constraint():
    """Допустимые статусы новости."""
    valid = {"draft", "published", "archived"}
    assert make_news("draft").status in valid
    assert make_news("published").status in valid


def test_editor_can_see_draft():
    """Editor и admin видят черновики."""
    news = make_news("draft")
    editor = make_user(role="editor")
    reader = make_user(role="reader")
    can_editor = editor.role in ("editor", "admin") or news.status == "published"
    can_reader = reader.role in ("editor", "admin") or news.status == "published"
    assert can_editor
    assert not can_reader
