"""
Скрипт миграции KB: конвертация HTML-контента статей в Markdown.

Использование:
    python scripts/migrate_kb_html_to_md.py [--dry-run] [--article-id <uuid>]

Флаги:
    --dry-run       Показать что будет изменено, не сохраняя в БД
    --article-id    Мигрировать только конкретную статью

Логика:
    1. Находит все статьи где body начинается с '<' (HTML) и не является пустым
    2. Конвертирует через markdownify (html → markdown)
    3. Обновляет поле body в БД (idempotent — повторный запуск безопасен)
    4. Логирует результат: сколько статей обновлено, пропущено, ошибок
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from markdownify import markdownify as md
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.kb import KbArticle

logger = get_logger(__name__)


def html_to_markdown(html: str) -> str:
    """Конвертирует HTML в Markdown через markdownify."""
    result = md(
        html,
        heading_style="ATX",
        bullets="-",
        strong_em_symbol="*",
        newline_style="backslash",
        strip=["script", "style"],
    )
    lines = result.splitlines()
    cleaned = []
    prev_blank = False
    for line in lines:
        stripped = line.rstrip()
        is_blank = stripped == ""
        if is_blank and prev_blank:
            continue
        cleaned.append(stripped)
        prev_blank = is_blank

    return "\n".join(cleaned).strip()


def looks_like_html(text: str) -> bool:
    """Простая эвристика: начинается с '<' или содержит HTML-теги."""
    stripped = text.strip()
    if stripped.startswith("<"):
        return True
    html_markers = [
        "<p>",
        "<div>",
        "<h1>",
        "<h2>",
        "<h3>",
        "<ul>",
        "<ol>",
        "<br>",
        "<br/>",
        "<strong>",
        "<em>",
    ]
    lower = stripped.lower()
    return any(m in lower for m in html_markers)


async def migrate(dry_run: bool = False, article_id: str | None = None) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {"converted": 0, "skipped": 0, "errors": 0, "already_md": 0}

    async with async_session() as session:
        stmt = select(KbArticle).where(KbArticle.deleted_at.is_(None))
        if article_id:
            try:
                art_uuid = uuid.UUID(article_id)
            except ValueError:
                logger.error("Invalid article UUID", article_id=article_id)
                return
            stmt = stmt.where(KbArticle.id == art_uuid)

        result = await session.execute(stmt)
        articles = result.scalars().all()

        logger.info("Found articles to check", total=len(articles))

        for article in articles:
            if not article.body:
                stats["skipped"] += 1
                continue

            if not looks_like_html(article.body):
                stats["already_md"] += 1
                continue

            try:
                converted = html_to_markdown(article.body)
            except Exception as e:
                logger.error(
                    "Failed to convert article",
                    article_id=str(article.id),
                    title=article.title,
                    error=str(e),
                )
                stats["errors"] += 1
                continue

            if dry_run:
                logger.info(
                    "[DRY RUN] Would convert article",
                    article_id=str(article.id),
                    title=article.title,
                    original_len=len(article.body),
                    converted_len=len(converted),
                )
                stats["converted"] += 1
                continue

            await session.execute(
                update(KbArticle).where(KbArticle.id == article.id).values(body=converted)
            )
            stats["converted"] += 1
            logger.info(
                "Converted article",
                article_id=str(article.id),
                title=article.title,
                original_len=len(article.body),
                converted_len=len(converted),
            )

        if not dry_run:
            await session.commit()

    await engine.dispose()

    logger.info(
        "Migration complete",
        converted=stats["converted"],
        already_markdown=stats["already_md"],
        skipped=stats["skipped"],
        errors=stats["errors"],
        dry_run=dry_run,
    )

    if stats["errors"] > 0:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate KB articles from HTML to Markdown")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without saving")
    parser.add_argument(
        "--article-id", type=str, default=None, help="Migrate only specific article UUID"
    )
    args = parser.parse_args()

    asyncio.run(migrate(dry_run=args.dry_run, article_id=args.article_id))


if __name__ == "__main__":
    main()
