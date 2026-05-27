"""Unit-тесты services/kb.py (Phase 3.2).

Покрытие:
- _slugify: простые строки
- record_article_view: дедупликация через Redis / first view
- _resolve_tags: пустой список / создание новых тегов / возврат существующих
- set_article_tags: очищает старые теги, добавляет новые
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── _slugify ───────────────────────────────────────────────────────────────────


def test_slugify_ascii():
    from app.services.kb import _slugify

    assert _slugify("Hello World") == "hello-world"


def test_slugify_empty_uses_fallback():
    from app.services.kb import _slugify

    result = _slugify("")
    assert result == "section"


def test_slugify_cyrillic_uses_fallback():
    from app.services.kb import _slugify

    result = _slugify("Привет")
    assert isinstance(result, str)
    assert len(result) > 0


# ── record_article_view ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_article_view_deduplicates():
    from app.services.kb import record_article_view

    db = AsyncMock()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=None)

    article_id = uuid.uuid4()
    user_id = uuid.uuid4()

    result = await record_article_view(db, redis, article_id, user_id)

    assert result is False
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_record_article_view_first_view():
    from app.services.kb import record_article_view

    db = AsyncMock()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    article_id = uuid.uuid4()
    user_id = uuid.uuid4()

    result = await record_article_view(db, redis, article_id, user_id)

    assert result is True
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()
    redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_article_view_sets_correct_key():
    from app.services.kb import record_article_view

    db = AsyncMock()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    article_id = uuid.uuid4()
    user_id = uuid.uuid4()

    await record_article_view(db, redis, article_id, user_id)

    redis.set.assert_awaited_once()
    call_args = redis.set.call_args[0][0]
    assert str(article_id) in call_args
    assert str(user_id) in call_args


# ── _resolve_tags ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_tags_empty_list():
    from app.services.kb import _resolve_tags

    db = AsyncMock()
    result = await _resolve_tags(db, [])

    assert result == []
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_tags_creates_new_tag():
    from app.services.kb import _resolve_tags

    db = AsyncMock()
    db.add = MagicMock()

    execute_result = MagicMock()
    execute_result.scalars.return_value = MagicMock(
        __iter__=MagicMock(return_value=iter([]))
    )
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()

    tags = await _resolve_tags(db, ["New Tag"])

    assert len(tags) == 1
    db.add.assert_called_once()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_tags_returns_existing():
    from app.services.kb import _resolve_tags

    db = AsyncMock()

    existing_tag = MagicMock()
    existing_tag.slug = "existing-tag"
    existing_tag.name = "Existing Tag"

    execute_result = MagicMock()
    execute_result.scalars.return_value = MagicMock(
        __iter__=MagicMock(return_value=iter([existing_tag]))
    )
    db.execute = AsyncMock(return_value=execute_result)

    tags = await _resolve_tags(db, ["Existing Tag"])

    assert len(tags) == 1
    assert tags[0].slug == "existing-tag"
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_tags_mixed_new_and_existing():
    from app.services.kb import _resolve_tags

    db = AsyncMock()
    db.add = MagicMock()

    existing_tag = MagicMock()
    existing_tag.slug = "existing"
    existing_tag.name = "Existing"

    execute_result = MagicMock()
    execute_result.scalars.return_value = MagicMock(
        __iter__=MagicMock(return_value=iter([existing_tag]))
    )
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()

    tags = await _resolve_tags(db, ["Existing", "Brand New"])

    assert len(tags) == 2
    db.add.assert_called_once()


# ── set_article_tags ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_article_tags_clears_and_adds():
    from app.services.kb import set_article_tags

    db = AsyncMock()
    db.add = MagicMock()

    tag1 = MagicMock()
    tag1.id = uuid.uuid4()
    tag1.slug = "tag-one"
    tag1.name = "Tag One"

    execute_result = MagicMock()
    execute_result.scalars.return_value = MagicMock(
        __iter__=MagicMock(return_value=iter([tag1]))
    )
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()

    article = MagicMock()
    article.id = uuid.uuid4()

    await set_article_tags(db, article, ["Tag One"])

    assert db.execute.call_count >= 2
    db.add.assert_called()


@pytest.mark.asyncio
async def test_set_article_tags_empty_clears_all():
    from app.services.kb import set_article_tags

    db = AsyncMock()
    db.execute = AsyncMock()

    article = MagicMock()
    article.id = uuid.uuid4()

    await set_article_tags(db, article, [])

    db.execute.assert_awaited_once()
    db.add.assert_not_called()
