"""Ретеншен одноразовых кодов входа (learning, passwordless).

``learning_login_codes`` (миграция 113) растёт на строку каждый вход; строки
без очистки не мешают работе (поиск по account_id), но копятся — cron раз
в сутки удаляет использованные и просроченные старше 30 дней. Попытки и
прогресс НЕ трогаем — это история обучения (§7 ТЗ). Реликтная
``learning_password_resets`` дропнута миграцией 114.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, and_, delete, or_

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.learning import LearningLoginCode

logger = get_logger(__name__)

RETENTION_DAYS = 30


async def cleanup_expired_resets(ctx: dict) -> int:
    """Удалить использованные/просроченные коды старше RETENTION_DAYS."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(LearningLoginCode).where(
                and_(
                    LearningLoginCode.created_at < cutoff,
                    or_(
                        LearningLoginCode.used_at.is_not(None),
                        LearningLoginCode.expires_at < now,
                    ),
                )
            )
        )
        await db.commit()
    deleted = int(cast(CursorResult, result).rowcount or 0)
    if deleted:
        logger.info("learning.login_codes_cleaned", deleted=deleted)
    return deleted
