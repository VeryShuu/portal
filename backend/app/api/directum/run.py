"""Ручной прогон Directum: ``POST /directum/run`` (docs/directum.md).

Ставит ARQ-задачу ``run_directum_sync(triggered_by='manual')`` — та же логика,
что cron, но немедленно и без interval-guard/overdue_enabled (админ явно хочет
«прямо сейчас»; правило «уведомлять каждый прогон» осознанно распространяется
и на ручные запуски).

UX-урок (инцидент 2026-08-17 «крутится и ничего не происходит»):

* Фиксированный ``_job_id`` на админа дедуплицировался ARQ по ключу
  ``arq:job:<id>`` (~1 час TTL) — повторные нажатия молча отбрасывались.
  Теперь job-id уникален на каждое нажатие; от спама двойными кликами
  защищает distributed-lock воркера (``directum:poll_lock``), а не дедуп.
* Прогон при выключенном ``settings.enabled`` раньше молча скипался в воркере
  (run-строку скип не создаёт) — кнопка крутилась 90 секунд впустую. Теперь
  API отвечает 400 сразу, с понятной причиной.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import AdminDep, DbDep, require_directum_module
from app.core.logging import get_logger
from app.schemas.directum import DirectumRunNowResponse
from app.services.directum.sync import directum_configured, load_directum_settings

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_directum_module)])


@router.post("/run", response_model=DirectumRunNowResponse)
async def run_now(admin: AdminDep, db: DbDep, request: Request) -> DirectumRunNowResponse:
    """Поставить прогон в ARQ-очередь (немедленно, не ждать cron)."""
    settings = await load_directum_settings(db)
    if settings is None or not directum_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Directum credentials are not configured (see settings)",
        )
    if not settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Directum module is off — enable «Модуль включён» in the tab settings",
        )

    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task queue unavailable",
        )
    # Короткое имя функции (AGENTS.md: НЕ FQN для enqueue_job). Уникальный
    # суффикс: дедуп по фиксированному job-id молча глотал повторы в течение
    # часа после первого нажатия (см. docstring модуля).
    job = await pool.enqueue_job(
        "run_directum_sync",
        triggered_by="manual",
        _job_id=f"directum:run:{admin.id}:{uuid4().hex[:12]}",
    )
    if job is None:
        # Коллизия уникального id — практически невозможна; отвечаем честно.
        return DirectumRunNowResponse(status="queued", job_id=None)
    logger.info("directum.run_enqueued", by=str(admin.id), job_id=job.job_id)
    return DirectumRunNowResponse(status="queued", job_id=job.job_id)
