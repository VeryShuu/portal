"""Backfill cover variants and dominant color for existing news.

Использование (внутри backend-контейнера):
    python -m scripts.backfill_news_covers              # все обложки без вариантов
    python -m scripts.backfill_news_covers --all        # перегенерировать всё
    python -m scripts.backfill_news_covers --dry-run    # без записи в БД

Скрипт идемпотентен: при повторном запуске пропускает обложки, у которых
уже есть cover_variants и cover_dominant_color (если не указан --all).
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal as async_session_factory
from app.core.logging import get_logger
from app.models.news import News
from app.services.news import _NEWS_MEDIA_DIR, _build_cover_variants, _remove_cover_variants

logger = get_logger(__name__)


async def _process_one(session, item: News, regen: bool, dry_run: bool) -> str:
    if not item.cover_image:
        return "skip-no-cover"
    if not regen and item.cover_variants and item.cover_dominant_color:
        return "skip-already-done"

    src = _NEWS_MEDIA_DIR / item.cover_image
    if not src.exists():
        return "skip-missing-file"

    out_dir = _NEWS_MEDIA_DIR / str(item.id)
    if regen:
        _remove_cover_variants(out_dir)

    widths, dominant = await asyncio.to_thread(_build_cover_variants, src, out_dir)
    if dry_run:
        return f"would-update widths={widths} color={dominant}"

    await session.execute(
        update(News)
        .where(News.id == item.id)
        .values(
            cover_dominant_color=dominant,
            cover_variants=widths or None,
            updated_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return f"updated widths={widths} color={dominant}"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Перегенерировать даже там, где уже заполнено")
    parser.add_argument("--dry-run", action="store_true", help="Не писать в БД")
    parser.add_argument("--limit", type=int, default=0, help="Ограничение (0 = без ограничения)")
    args = parser.parse_args()

    async with async_session_factory() as session:
        stmt = select(News).where(News.cover_image.is_not(None)).order_by(News.created_at.desc())
        if args.limit:
            stmt = stmt.limit(args.limit)
        rows = (await session.execute(stmt)).scalars().all()

        print(f"[backfill] candidates: {len(rows)}")
        stats: dict[str, int] = {}
        for i, item in enumerate(rows, 1):
            try:
                result = await _process_one(session, item, regen=args.all, dry_run=args.dry_run)
            except Exception as e:
                result = f"error: {e!s}"
                logger.exception("backfill.failed", news_id=str(item.id))
            stats[result.split(" ")[0]] = stats.get(result.split(" ")[0], 0) + 1
            print(f"[{i}/{len(rows)}] {item.id} -> {result}")

        print("\n[backfill] summary:")
        for k, v in sorted(stats.items()):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
