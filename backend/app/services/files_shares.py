"""Сервисные операции пофайлового шеринга (production-оркестрация).

audit-review 2026-08-22 (P1 «тесты обходят production orchestration»):
отзыв шеры и инвалидация кэша обязаны жить в одной функции, которую вызывает
и роутер, и тест — удаление invalidation из API не должно оставаться
незамеченным для integration-тестов. Раньше логика лежала в роутере
(``api/files/shares.py::revoke_file_share``), и тесты воспроизводили её руками.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.files.repo import find_share_by_id
from app.models.files import FileShare
from app.services.files_acl import invalidate_file_share_cache


async def revoke_share(
    db: AsyncSession,
    redis: Redis,
    *,
    folder_id: uuid.UUID,
    filename: str,
    share_id: uuid.UUID,
) -> FileShare:
    """Отозвать шеру файла (мягко, ``revoked_at``) + инвалидировать кэш.

    ACL-проверку (manager папки) выполняет роутер ДО вызова — здесь только
    транзакционная часть: пометка отзыва, commit, сброс кэша прав. Идемпотентна:
    повторный отзыв уже отозванной шеры — no-op (история не затирается).
    Возвращает модель шеры (``revoked_at`` установлен).
    """
    share = await find_share_by_id(db, folder_id=folder_id, filename=filename, share_id=share_id)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")

    if share.revoked_at is None:
        share.revoked_at = datetime.now(UTC)
        await db.commit()

    # Инвалидация обязана следовать за отзывом в одном вызове: без неё
    # резолвер до 300с (TTL) продолжает выдавать доступ отозванной шеры.
    await invalidate_file_share_cache(redis, folder_id, filename)
    return share
