"""KB hard-delete (purge).

Удаляет статью KB полностью (БД + файлы на диске) и чистит сирот.
Используется как одиночным admin-эндпоинтом ``POST /kb/articles/{id}/purge``,
так и фоновой задачей ``purge_kb_trash`` (см. ``app.worker.tasks.kb``).
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.kb import KbArticle

logger = get_logger(__name__)

# Размер батча для bulk-purge: один DELETE + commit на чанк.
PURGE_BATCH_SIZE = 100
# Параллелизм rmtree (защита диска от спайка I/O).
RMTREE_CONCURRENCY = 8


def _kb_files_root() -> Path:
    return Path(get_settings().kb_files_dir).resolve()


def _kb_media_root() -> Path:
    return Path(get_settings().kb_media_dir).resolve()


async def _rmtree(path: Path) -> None:
    if not path.exists():
        return
    try:
        await asyncio.to_thread(shutil.rmtree, str(path), True)
    except Exception as exc:
        logger.warning(
            "kb.purge.rmtree_failed",
            path=str(path),
            error=str(exc),
        )


async def remove_article_dirs(article_id: uuid.UUID) -> None:
    """Удаляет каталоги вложений и медиа статьи с диска."""
    await _rmtree(_kb_files_root() / str(article_id))
    await _rmtree(_kb_media_root() / str(article_id))


async def try_remove_empty_article_dir(
    article_id: uuid.UUID, kind: str
) -> None:
    """Удаляет пустую директорию (`kind` ∈ {"files", "media"}). Молча игнорирует, если не пуста."""
    root = _kb_files_root() if kind == "files" else _kb_media_root()
    target = root / str(article_id)
    if not target.exists():
        return
    try:
        await asyncio.to_thread(target.rmdir)
    except OSError:
        return
    except Exception as exc:
        logger.debug(
            "kb.purge.rmdir_failed",
            path=str(target),
            error=str(exc),
        )


async def _parallel_remove_dirs(article_ids: list[uuid.UUID]) -> None:
    """Удаляет каталоги статей параллельно с ограничением concurrency."""
    if not article_ids:
        return
    sem = asyncio.Semaphore(RMTREE_CONCURRENCY)

    async def _one(aid: uuid.UUID) -> None:
        async with sem:
            await remove_article_dirs(aid)

    await asyncio.gather(*[_one(a) for a in article_ids])


async def purge_article(db: AsyncSession, article_id: uuid.UUID) -> bool:
    """Полностью удаляет статью из БД (cascade приберёт связанные таблицы)
    и убирает её каталоги на диске. Возвращает True, если статья была удалена.

    Используется SQL-level DELETE вместо ORM ``db.delete(article)``: ORM пытается
    nullify FK у `versions` (relationship без ``passive_deletes``), что нарушает
    NOT NULL на ``kb_article_versions.article_id``. Прямой DELETE отдаёт каскад
    на уровень БД (``ondelete="CASCADE"`` на FK).
    """
    res = await db.execute(
        delete(KbArticle).where(KbArticle.id == article_id)
    )
    await db.commit()
    if res.rowcount == 0:
        return False
    await remove_article_dirs(article_id)
    return True


async def _purge_ids_batched(
    db: AsyncSession, ids: list[uuid.UUID]
) -> int:
    """Удаляет статьи чанками PURGE_BATCH_SIZE: 1 DELETE + 1 commit на чанк,
    после каждого чанка — параллельный rmtree директорий.
    Возвращает количество удалённых записей.
    """
    if not ids:
        return 0
    total = 0
    for start in range(0, len(ids), PURGE_BATCH_SIZE):
        chunk = ids[start : start + PURGE_BATCH_SIZE]
        res = await db.execute(delete(KbArticle).where(KbArticle.id.in_(chunk)))
        await db.commit()
        deleted = res.rowcount or 0
        total += deleted
        if deleted:
            await _parallel_remove_dirs(chunk)
    return total


async def purge_articles_bulk(
    db: AsyncSession, article_ids: list[uuid.UUID]
) -> int:
    """Bulk-purge произвольного набора статей (чанками, с параллельным rmtree)."""
    return await _purge_ids_batched(db, list(article_ids))


async def purge_all_trash(db: AsyncSession) -> int:
    """Удаляет (БД + диск) ВСЕ soft-deleted статьи чанками по PURGE_BATCH_SIZE.

    Чтобы не грузить в память миллион id, читаем по странице, удаляем, повторяем.
    """
    total = 0
    while True:
        ids_res = await db.execute(
            select(KbArticle.id)
            .where(KbArticle.deleted_at.isnot(None))
            .limit(PURGE_BATCH_SIZE)
        )
        chunk = [row[0] for row in ids_res.fetchall()]
        if not chunk:
            break
        res = await db.execute(delete(KbArticle).where(KbArticle.id.in_(chunk)))
        await db.commit()
        deleted = res.rowcount or 0
        total += deleted
        if deleted:
            await _parallel_remove_dirs(chunk)
        if deleted < len(chunk):
            # На случай, если что-то ушло другим процессом.
            continue
    if total:
        logger.info("kb.purge.all_done", count=total)
    return total


async def purge_expired_articles(
    db: AsyncSession, retention_days: int
) -> int:
    """Удаляет (DB + диск) все статьи, у которых ``deleted_at`` старше retention.

    Если ``retention_days`` <= 0 — задача отключена (ничего не делает).
    Чанками PURGE_BATCH_SIZE, чтобы не блокировать БД и не раздувать память.
    Возвращает количество удалённых статей.
    """
    if retention_days <= 0:
        return 0
    threshold = datetime.now(UTC) - timedelta(days=retention_days)
    total = 0
    while True:
        ids_res = await db.execute(
            select(KbArticle.id)
            .where(
                KbArticle.deleted_at.isnot(None),
                KbArticle.deleted_at < threshold,
            )
            .limit(PURGE_BATCH_SIZE)
        )
        chunk = [row[0] for row in ids_res.fetchall()]
        if not chunk:
            break
        res = await db.execute(delete(KbArticle).where(KbArticle.id.in_(chunk)))
        await db.commit()
        deleted = res.rowcount or 0
        total += deleted
        if deleted:
            await _parallel_remove_dirs(chunk)
        if deleted < len(chunk):
            continue
    if total:
        logger.info(
            "kb.purge.expired_done", count=total, retention_days=retention_days
        )
    return total


async def cleanup_orphan_dirs(db: AsyncSession) -> int:
    """Удаляет каталоги в kb_files_dir / kb_media_dir, которым не соответствует
    ни одна запись статьи (даже soft-deleted) в БД. Возвращает количество удалённых каталогов.

    Защита: каждая entry проверяется на принадлежность root после ``resolve()`` —
    отбрасываем симлинки наружу.
    """
    res = await db.execute(select(KbArticle.id))
    known = {str(r[0]) for r in res.fetchall()}
    removed = 0
    for root in (_kb_files_root(), _kb_media_root()):
        if not root.exists():
            continue
        try:
            entries = await asyncio.to_thread(list, root.iterdir())
        except Exception as exc:
            logger.warning("kb.purge.orphan_scan_failed", path=str(root), error=str(exc))
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            try:
                uuid.UUID(entry.name)
            except ValueError:
                continue
            if entry.name in known:
                continue
            try:
                real = entry.resolve()
            except OSError:
                continue
            try:
                real.relative_to(root)
            except ValueError:
                logger.warning(
                    "kb.purge.orphan_skipped_outside_root",
                    path=str(entry),
                    real=str(real),
                )
                continue
            await _rmtree(entry)
            removed += 1
    if removed:
        logger.info("kb.purge.orphans_removed", count=removed)
    return removed


__all__ = [
    "PURGE_BATCH_SIZE",
    "cleanup_orphan_dirs",
    "purge_all_trash",
    "purge_article",
    "purge_articles_bulk",
    "purge_expired_articles",
    "remove_article_dirs",
    "try_remove_empty_article_dir",
]
