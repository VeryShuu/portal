"""ARQ-задачи для модуля «База знаний»:

- ``purge_kb_trash`` — раз в сутки удаляет soft-deleted статьи старше retention
  (БД + каталоги вложений/медиа на диске).
- ``cleanup_kb_orphan_dirs`` — раз в сутки удаляет каталоги в kb_files_dir /
  kb_media_dir, для которых нет ни одной записи статьи в БД (даже soft-deleted).
"""

from __future__ import annotations

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.system_config import load_system_settings
from app.services.kb_trash import cleanup_orphan_dirs, purge_expired_articles

logger = get_logger(__name__)


async def purge_kb_trash(ctx: dict) -> int:
    """Удаляет soft-deleted статьи старше ``kb_trash_retention_days``."""
    retention = load_system_settings().kb_trash_retention_days
    if retention <= 0:
        logger.info("kb.purge.disabled", reason="retention_days_le_0")
        return 0
    async with AsyncSessionLocal() as session:
        removed = await purge_expired_articles(session, retention)
    return removed


async def cleanup_kb_orphan_dirs(ctx: dict) -> int:
    """Чистит каталоги без соответствующих статей в БД."""
    async with AsyncSessionLocal() as session:
        removed = await cleanup_orphan_dirs(session)
    return removed


__all__ = [
    "cleanup_kb_orphan_dirs",
    "purge_kb_trash",
]
