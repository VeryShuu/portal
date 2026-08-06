"""Ручной запуск импорта отсутствий: mailbox-trigger + multipart-upload.

Клон :mod:`run` (поток дней рождения), но использует общий ``run_absences_import``.

* ``POST /erp-sync/absences/run`` — ставит ARQ-задачу
  ``run_erp_absences_sync(triggered_by=manual)``. Та же cron-логика, но немедленно.
* ``POST /erp-sync/absences/import-file`` — принимает файл напрямую (multipart),
  парсит и импортирует синхронно через общий ``run_absences_import``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status

from app.api.deps import AdminDep, DbDep, RedisDep, require_erp_sync_module
from app.core.logging import get_logger
from app.schemas.erp_sync import ErpSyncRunNowResponse
from app.services.email_settings import imap_configured, load_email_settings
from app.services.erp_sync.absences_importer import (
    AbsenceAttachment,
    absence_attachment_hash,
    run_absences_import,
)
from app.services.erp_sync.parser import SUPPORTED_FORMATS, detect_format

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_erp_sync_module)])

# Лимит размера загружаемого файла (клон run.py — 50 MiB с большим запасом).
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/absences/run", response_model=ErpSyncRunNowResponse)
async def run_absences_now(
    admin: AdminDep,
    request: Request,
) -> ErpSyncRunNowResponse:
    """Поставить mailbox-poll отсутствий в ARQ-очередь (немедленно).

    ``absences_poll_enabled`` НЕ проверяется (админ явно хочет «забрать сейчас»),
    но общий IMAP должен быть настроен (ADR-048).
    """
    if not imap_configured(load_email_settings()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IMAP mailbox is not configured (see Email tab)",
        )

    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task queue unavailable",
        )
    # Короткое имя функции (AGENTS.md: НЕ FQN для enqueue_job).
    job = await pool.enqueue_job(
        "run_erp_absences_sync",
        triggered_by="manual",
        _job_id=f"erp_absences:run:{admin.id}",
    )
    if job is None:
        return ErpSyncRunNowResponse(
            status="queued",
            job_id=f"erp_absences:run:{admin.id}",
        )
    logger.info("erp_absences.run_enqueued", by=str(admin.id), job_id=job.job_id)
    return ErpSyncRunNowResponse(status="queued", job_id=job.job_id)


@router.post("/absences/import-file", response_model=ErpSyncRunNowResponse)
async def import_absences_file(
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
    file: UploadFile,
) -> ErpSyncRunNowResponse:
    """Импортировать файл отсутствий напрямую (multipart-upload), синхронно.

    Общий ``run_absences_import`` с mailbox — отличие только в источнике
    :class:`AbsenceAttachment`. ``message_id=None`` (нет письма; дедуп по hash
    не делаем — каждый upload новый, для перезапуска при отладке).
    """
    filename = file.filename or "upload.bin"
    if detect_format(filename) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неподдерживаемый формат. Допустимо: {', '.join(SUPPORTED_FORMATS)}.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл пуст.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл слишком большой (лимит {_MAX_UPLOAD_BYTES // (1024 * 1024)} MiB).",
        )

    run = await run_absences_import(
        db,
        redis,
        attachment=AbsenceAttachment(
            filename=filename, data=data, hash=absence_attachment_hash(data)
        ),
        message_id=None,
        triggered_by="manual",
    )
    logger.info(
        "erp_absences.import_file_done",
        run_id=run.id,
        filename=filename,
        by=str(admin.id),
    )
    return ErpSyncRunNowResponse(status="processed", run_id=run.id)
