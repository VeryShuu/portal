"""Очистка истории прогонов интеграционных модулей (решение 2026-08-17).

Админу история старше 7 дней не нужна ни в ERP-блоке, ни в Directum —
хардкод-ретеншн (без настроек): cron ежедневно удаляет runs-строки старше
``RETENTION_DAYS`` из:

* ``erp_sync_runs`` (дни рождения);
* ``erp_absences_runs`` (отсутствия);
* ``directum_runs`` (просроченные задачи).

Отчёты emailed в момент прогона уже доставлены — история в админке нужна для
свежего разбора, старые строки только шумят в пагинации.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.directum import DirectumRun
from app.models.erp_sync import ErpAbsencesRun, ErpSyncRun

logger = get_logger(__name__)

RETENTION_DAYS = 7


async def cleanup_module_runs(ctx: dict) -> dict:
    """Раз в день удалить runs-строки старше RETENTION_DAYS дней."""
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    deleted: dict[str, int] = {}
    async with AsyncSessionLocal() as session, session.begin():
        for label, model in (
            ("erp_sync_runs", ErpSyncRun),
            ("erp_absences_runs", ErpAbsencesRun),
            ("directum_runs", DirectumRun),
        ):
            result = await session.execute(delete(model).where(model.started_at < cutoff))
            deleted[label] = int(cast(CursorResult, result).rowcount or 0)
    logger.info("runs.cleanup_done", **deleted, retention_days=RETENTION_DAYS)
    return deleted
