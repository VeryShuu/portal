"""Ручной запуск импорта: mailbox-trigger + multipart-upload (docs/wip/erp-sync.md).

Два режима:

* ``POST /erp-sync/run`` — ставит ARQ-задачу ``run_erp_sync(triggered_by=manual)``.
  Та же cron-логика, но немедленно. Возвращает ``job_id`` для отслеживания.
  Удобно, когда админ знает, что письмо пришло, и не хочет ждать 15 мин.
* ``POST /erp-sync/import-file`` — принимает файл напрямую (multipart), парсит
  и импортирует синхронно через общий ``run_import``. Не требует mailbox —
  идеален для первичной настройки, диагностики проблемных выгрузок и миграции.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.api.deps import AdminDep, DbDep, RedisDep, require_erp_sync_module
from app.core.logging import get_logger
from app.models.erp_sync import ErpSyncSettings
from app.schemas.erp_sync import ErpSyncRunNowResponse
from app.services.erp_sync.importer import Attachment, attachment_hash, run_import
from app.services.erp_sync.parser import SUPPORTED_FORMATS, detect_format

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_erp_sync_module)])

# Лимит размера загружаемого файла (50 MiB — отчёт 1С на ~300 чел. занимает
# сотни КБ; 50 MiB — с большим запасом, защита от случайной загрузки).
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/run", response_model=ErpSyncRunNowResponse)
async def run_now(
    admin: AdminDep,
    db: DbDep,
    request: Request,
) -> ErpSyncRunNowResponse:
    """Поставить mailbox-poll в ARQ-очередь (немедленно, не ждать cron).

    Импорт выполнится в воркере с ``triggered_by='manual'``. ``poll_enabled``
    НЕ проверяется (админ явно хочет «забрать сейчас»), но IMAP должен быть
    настроен — задача вернёт ``imap_not_configured``, если нет.
    """
    # Защита: mailbox должен быть настроен.
    settings = (
        await db.execute(select(ErpSyncSettings).where(ErpSyncSettings.id == 1))
    ).scalar_one_or_none()
    if settings is None or not settings.imap_host or not settings.imap_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IMAP mailbox is not configured",
        )

    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task queue unavailable",
        )
    # Короткое имя функции (AGENTS.md: НЕ FQN для enqueue_job).
    job = await pool.enqueue_job(
        "run_erp_sync",
        triggered_by="manual",
        _job_id=f"erp_sync:run:{admin.id}",
    )
    if job is None:
        # Уже в очереди/выполняется (тот же _job_id) — не дублируем.
        return ErpSyncRunNowResponse(
            status="queued",
            job_id=f"erp_sync:run:{admin.id}",
        )
    logger.info("erp_sync.run_enqueued", by=str(admin.id), job_id=job.job_id)
    return ErpSyncRunNowResponse(status="queued", job_id=job.job_id)


@router.post("/import-file", response_model=ErpSyncRunNowResponse)
async def import_file(
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
    file: UploadFile,
) -> ErpSyncRunNowResponse:
    """Импортировать файл напрямую (multipart-upload), синхронно.

    Общий ``run_import`` с mailbox — отличие только в источнике ``Attachment``.
    ``message_id=None`` (нет письма; дедуп по hash не делаем — каждый upload
    новый, чтобы админ мог перезапустить импорт того же файла при отладке).
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

    run = await run_import(
        db,
        redis,
        attachment=Attachment(filename=filename, data=data, hash=attachment_hash(data)),
        message_id=None,
        triggered_by="manual",
    )
    logger.info(
        "erp_sync.import_file_done",
        run_id=run.id,
        filename=filename,
        by=str(admin.id),
    )
    return ErpSyncRunNowResponse(status="processed", run_id=run.id)
