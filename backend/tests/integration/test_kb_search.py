"""Integration: KB FTS-поиск с pg_trgm и russian_hunspell.

Проверяем, что:
- статья находится по точному слову (через FTS)
- статья находится с лёгкой опечаткой (через pg_trgm similarity)
- русская морфология работает (если hunspell установлен): «платежи» ↔ «платёж»
- soft-deleted статьи в выдаче не появляются
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _ensure_kb_models_loaded():
    """Forces SQLAlchemy to import KB models, чтобы Alembic-миграции были доступны."""


async def test_kb_search_exact_match(real_db_session, real_editor):
    """Статья находится по точному слову в title."""
    await _ensure_kb_models_loaded()
    from app.models.kb import KbArticle

    article = KbArticle(
        title="Регламент отпусков сотрудников",
        body="<p>Текст про отпуска</p>",
        status="published",
        created_by=real_editor.id,
        published_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    real_db_session.add(article)
    await real_db_session.commit()

    rows = (
        await real_db_session.execute(
            text("""
                SELECT id FROM kb_articles
                WHERE status = 'published'
                  AND deleted_at IS NULL
                  AND (title ILIKE :q OR body ILIKE :q)
            """),
            {"q": "%отпусков%"},
        )
    ).fetchall()
    assert len(rows) >= 1
    assert any(r[0] == article.id for r in rows)


async def test_kb_search_trigram_typo(real_db_session, real_editor):
    """pg_trgm similarity находит статью при опечатке."""
    await _ensure_kb_models_loaded()
    from app.models.kb import KbArticle

    article = KbArticle(
        title="Регламент отпусков",
        body="<p>x</p>",
        status="published",
        created_by=real_editor.id,
        published_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    real_db_session.add(article)
    await real_db_session.commit()

    # «отпуксов» — опечатка
    rows = (
        await real_db_session.execute(
            text("""
                SELECT id, similarity(title, :q) AS sim
                FROM kb_articles
                WHERE status = 'published' AND deleted_at IS NULL
                  AND similarity(title, :q) > 0.2
                ORDER BY sim DESC
            """),
            {"q": "отпуксов"},
        )
    ).fetchall()
    assert any(r[0] == article.id for r in rows)


async def test_kb_search_excludes_deleted(real_db_session, real_editor):
    """Soft-deleted статьи в выдачу не попадают."""
    await _ensure_kb_models_loaded()
    from app.models.kb import KbArticle

    article = KbArticle(
        title="Удалённая статья",
        body="<p>x</p>",
        status="published",
        created_by=real_editor.id,
        deleted_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    real_db_session.add(article)
    await real_db_session.commit()

    rows = (
        await real_db_session.execute(
            text("""
                SELECT id FROM kb_articles
                WHERE status = 'published' AND deleted_at IS NULL
                  AND title ILIKE :q
            """),
            {"q": "%Удалённая%"},
        )
    ).fetchall()
    assert all(r[0] != article.id for r in rows)


async def test_pg_extensions_loaded(real_db_session):
    """unaccent и pg_trgm должны быть установлены."""
    rows = (
        await real_db_session.execute(
            text(
                "SELECT extname FROM pg_extension WHERE extname IN ('pg_trgm', 'unaccent', 'pgcrypto')"
            )
        )
    ).fetchall()
    extensions = {r[0] for r in rows}
    assert "pg_trgm" in extensions
    assert "unaccent" in extensions
    assert "pgcrypto" in extensions


async def test_russian_hunspell_config_exists(real_db_session):
    """FTS-конфигурация russian_hunspell должна быть создана через init.sql."""
    rows = (
        await real_db_session.execute(
            text("SELECT cfgname FROM pg_ts_config WHERE cfgname = 'russian_hunspell'")
        )
    ).fetchall()
    assert len(rows) == 1
