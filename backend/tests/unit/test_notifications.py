"""Unit-тесты для системы уведомлений Phase 4."""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_notification(**kwargs):
    from app.models.notification import Notification

    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        type="news_published",
        title="Test notification",
        body=None,
        link="/news/1",
        is_read=False,
    )
    defaults.update(kwargs)
    n = MagicMock(spec=Notification)
    for k, v in defaults.items():
        setattr(n, k, v)
    return n


# ── STREAM KEY ────────────────────────────────────────────────────────────────

def test_stream_key_format():
    from app.services.notifications import NOTIFICATIONS_STREAM_KEY

    uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    key = NOTIFICATIONS_STREAM_KEY.format(user_id=str(uid))
    assert key == "notifications:12345678-1234-5678-1234-567812345678"


# ── _publish_to_stream ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_to_stream_calls_xadd():
    from app.services.notifications import _publish_to_stream

    redis = AsyncMock()
    notif = _make_notification()
    notif.created_at = MagicMock()
    notif.created_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"

    await _publish_to_stream(redis, user_id=notif.user_id, notification=notif)

    redis.xadd.assert_called_once()
    args, kwargs = redis.xadd.call_args
    key = args[0]
    assert str(notif.user_id) in key
    redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_publish_to_stream_handles_redis_error(caplog):
    from app.services.notifications import _publish_to_stream

    redis = AsyncMock()
    redis.xadd.side_effect = Exception("connection refused")
    notif = _make_notification()
    notif.created_at = MagicMock()
    notif.created_at.isoformat.return_value = "2026-01-01T00:00:00"

    await _publish_to_stream(redis, user_id=notif.user_id, notification=notif)
    # No exception propagated — fire-and-forget style


# ── notify_suggestion_reviewed ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_suggestion_reviewed_approve():
    from app.services.notifications import notify_suggestion_reviewed

    db = AsyncMock()
    redis = AsyncMock()

    user = MagicMock()
    user.id = uuid.uuid4()
    user.notify_inapp = True

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_suggestion_reviewed(
            db, redis,
            suggestion_author_id=user.id,
            article_id=uuid.uuid4(),
            article_title="Тестовая статья",
            action="approve",
        )
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert "одобрена" in call_kwargs["title"]
        assert call_kwargs["type"] == "suggestion_reviewed"


@pytest.mark.asyncio
async def test_notify_suggestion_reviewed_reject():
    from app.services.notifications import notify_suggestion_reviewed

    db = AsyncMock()
    redis = AsyncMock()

    user = MagicMock()
    user.id = uuid.uuid4()
    user.notify_inapp = True

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_suggestion_reviewed(
            db, redis,
            suggestion_author_id=user.id,
            article_id=uuid.uuid4(),
            article_title="Тестовая статья",
            action="reject",
        )
        call_kwargs = mock_create.call_args.kwargs
        assert "отклонена" in call_kwargs["title"]


@pytest.mark.asyncio
async def test_notify_suggestion_reviewed_skips_if_no_user():
    from app.services.notifications import notify_suggestion_reviewed

    db = AsyncMock()
    redis = AsyncMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_suggestion_reviewed(
            db, redis,
            suggestion_author_id=uuid.uuid4(),
            article_id=uuid.uuid4(),
            article_title="Статья",
            action="approve",
        )
        mock_create.assert_not_called()


# ── notify_users_news_published ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_users_news_published_targets_departments():
    from app.services.notifications import notify_users_news_published

    db = AsyncMock()
    redis = AsyncMock()

    user_it = MagicMock()
    user_it.id = uuid.uuid4()
    user_it.notify_inapp = True
    user_it.department = "IT"
    user_it.role = "reader"

    user_hr = MagicMock()
    user_hr.id = uuid.uuid4()
    user_hr.notify_inapp = True
    user_hr.department = "HR"
    user_hr.role = "reader"

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [user_it, user_hr]
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        sent = await notify_users_news_published(
            db, redis,
            news_id=uuid.uuid4(),
            news_title="IT Новость",
            target_departments=["IT"],
        )
        assert sent == 1
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["user_id"] == user_it.id


@pytest.mark.asyncio
async def test_notify_users_news_published_no_filter_notifies_all():
    from app.services.notifications import notify_users_news_published

    db = AsyncMock()
    redis = AsyncMock()

    users = [
        MagicMock(id=uuid.uuid4(), notify_inapp=True, department="IT", role="reader"),
        MagicMock(id=uuid.uuid4(), notify_inapp=True, department="HR", role="reader"),
        MagicMock(id=uuid.uuid4(), notify_inapp=True, department="Finance", role="editor"),
    ]

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = users
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        sent = await notify_users_news_published(
            db, redis,
            news_id=uuid.uuid4(),
            news_title="Общая новость",
        )
        assert sent == 3
        assert mock_create.call_count == 3


# ── Email builder ─────────────────────────────────────────────────────────────

def test_build_news_email_html_contains_title():
    from app.worker.tasks.notifications import _build_news_email_html

    html, text = _build_news_email_html("Важная новость", "http://portal/news/1", "Мой портал")
    assert "Важная новость" in html
    assert "Мой портал" in html
    assert "http://portal/news/1" in html
    assert "Важная новость" in text


def test_build_suggestion_email_html_approve():
    from app.worker.tasks.notifications import _build_suggestion_email_html

    html, text = _build_suggestion_email_html("Статья А", "http://portal/kb/1", "approve", "Портал")
    assert "одобрена" in html
    assert "одобрена" in text
    assert "#27ae60" in html


def test_build_suggestion_email_html_reject():
    from app.worker.tasks.notifications import _build_suggestion_email_html

    html, text = _build_suggestion_email_html("Статья Б", "http://portal/kb/2", "reject", "Портал")
    assert "отклонена" in html
    assert "#c0392b" in html


# ── SSE generator edge cases ──────────────────────────────────────────────────

def test_notifications_stream_key_per_user():
    from app.services.notifications import NOTIFICATIONS_STREAM_KEY

    uid1 = uuid.uuid4()
    uid2 = uuid.uuid4()
    key1 = NOTIFICATIONS_STREAM_KEY.format(user_id=str(uid1))
    key2 = NOTIFICATIONS_STREAM_KEY.format(user_id=str(uid2))
    assert key1 != key2


# ── get_unread_count ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_unread_count_returns_scalar():
    from app.services.notifications import get_unread_count

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one.return_value = 7
    db.execute.return_value = execute_result

    count = await get_unread_count(db, uuid.uuid4())
    assert count == 7
