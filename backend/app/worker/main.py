import asyncio
import contextlib

import asyncpg
from arq import cron, func
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
    restore_managed_loggers,
)
from app.worker.tasks.audit import cleanup_idempotency_keys
from app.worker.tasks.email_outbox import cleanup_email_outbox, process_email_outbox
from app.worker.tasks.files import startup_sync_nc_folders
from app.worker.tasks.helpdesk import (
    archive_closed_tickets_task,
    cleanup_helpdesk_attachments_task,
    create_next_helpdesk_archive_partition,
    poll_helpdesk_mailbox,
    send_helpdesk_digest,
)
from app.worker.tasks.kb import cleanup_kb_orphan_dirs, purge_kb_trash
from app.worker.tasks.meetings.email import send_meeting_email
from app.worker.tasks.metrics import (
    WORKER_HEARTBEAT_KEY,
    WORKER_HEARTBEAT_TTL,
    refresh_custom_metrics,
    worker_heartbeat,
)
from app.worker.tasks.news import close_expired_polls, sync_users_from_keycloak
from app.worker.tasks.notifications import (
    notify_news_published,
    send_email_notification,
)
from app.worker.tasks.photos import (
    cleanup_deleted_photos,
    cleanup_zip_jobs,
    detect_missing_thumbnails,
    empty_photo_trash,
    generate_folder_zip,
    import_scan_run,
    process_photo_upload,
)

settings = get_settings()
from app.core.system_config import (
    load_system_settings as _load_sys,
)
from app.core.system_config import (
    migrate_env_to_system_settings as _migrate_env,
)

# One-shot legacy env → JSON migration (see app.main for rationale).
_migrate_env()
_sys = _load_sys()
configure_logging(
    environment=settings.environment,
    log_level=_sys.log_level,
    service_name="portal-worker",
    force_json=_sys.log_force_json,
)
logger = get_logger(__name__)


async def _delayed_nc_sync(ctx: dict) -> None:
    await asyncio.sleep(30)
    await startup_sync_nc_folders(ctx)


async def startup(ctx: dict) -> None:
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    ctx["pg_pool"] = await asyncpg.create_pool(pg_url, min_size=1, max_size=5)
    await ctx["redis"].set(WORKER_HEARTBEAT_KEY, "1", ex=WORKER_HEARTBEAT_TTL)

    # ARQ CLI (python -m arq) выполняет собственный logging.config.dictConfig со
    # своим форматом уже после configure_logging в этом модуле — это перехватывает
    # логгер 'arq' голым текстовым handler и затирает structlog-процессоры.
    # Восстанавливаем structlog handler на MANAGED-логгерах и одновременно
    # приглушаем INFO о старте/успешном завершении высокочастотных cron-задач
    # (flush_audit_queue каждые 5с, process_email_outbox каждые 10с и т.д. —
    # ~145K строк шума за ~2 месяца на проде). Ошибки и редкие задачи остаются.
    from app.worker._arq_log_filter import QuietCronFilter

    restore_managed_loggers(
        level=_sys.log_level,
        extra_filters={"arq.worker": [QuietCronFilter()]},
    )

    # Чистим orphan arq:in-progress маркеры по photo-задачам и наши proc-локи,
    # оставшиеся от убитого/перезапущенного воркера. Без этого arq считает,
    # что job уже исполняется, и навсегда пропускает его в очереди.
    redis = ctx.get("redis")
    if redis is not None:
        for pattern in (
            "arq:in-progress:photos:*",
            "photos:proc-lock:*",
        ):
            try:
                cursor = 0
                removed = 0
                while True:
                    cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=500)
                    if keys:
                        await redis.delete(*keys)
                        removed += len(keys)
                    if cursor == 0:
                        break
                if removed:
                    logger.info("arq_worker.cleanup_orphan_keys", pattern=pattern, removed=removed)
            except Exception as exc:
                logger.warning(
                    "arq_worker.cleanup_orphan_keys_failed",
                    pattern=pattern,
                    error=str(exc),
                )
    logger.info("arq_worker.startup")
    _sync_task = asyncio.create_task(_delayed_nc_sync(ctx))
    ctx["_sync_task"] = _sync_task


async def shutdown(ctx: dict) -> None:
    # Отменяем отложенный nc-sync, если он ещё не отработал, чтобы не оставить
    # «висящую» задачу после остановки воркера.
    sync_task = ctx.get("_sync_task")
    if sync_task is not None and not sync_task.done():
        sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sync_task
    pool = ctx.get("pg_pool")
    if pool is not None:
        await pool.close()
    # NB: startup_sync_nc_folders сам захватывает и снимает свой Redis-lock через
    # token + compare-and-delete (см. tasks/files.py). Безусловный delete здесь
    # стирал бы лок, возможно принадлежащий другому воркеру, — поэтому убран.
    logger.info("arq_worker.shutdown")


async def on_job_start(ctx: dict) -> None:
    """Биндит job_id / job_try / function_name в contextvars для всех логов задачи."""
    clear_request_context()
    bind_request_context(
        job_id=ctx.get("job_id"),
        job_try=ctx.get("job_try"),
        function=(ctx.get("enqueue_time") and ctx.get("function")) or None,
        correlation_id=ctx.get("job_id"),  # job_id выступает correlation_id
    )


async def on_job_end(ctx: dict) -> None:
    clear_request_context()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = _sys.arq_max_jobs
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    on_job_end = on_job_end
    functions = [
        startup_sync_nc_folders,
        sync_users_from_keycloak,
        close_expired_polls,
        send_email_notification,
        notify_news_published,
        func(process_photo_upload, timeout=300, max_tries=5),
        func(cleanup_deleted_photos, timeout=300, max_tries=2),
        func(generate_folder_zip, timeout=600, max_tries=2),
        func(cleanup_zip_jobs, timeout=120, max_tries=2),
        func(detect_missing_thumbnails, timeout=300, max_tries=2),
        func(import_scan_run, timeout=600, max_tries=2),
        func(empty_photo_trash, timeout=300, max_tries=2),
        refresh_custom_metrics,
        cleanup_idempotency_keys,
        worker_heartbeat,
        send_meeting_email,
        process_email_outbox,
        cleanup_email_outbox,
        purge_kb_trash,
        cleanup_kb_orphan_dirs,
        poll_helpdesk_mailbox,
        archive_closed_tickets_task,
        create_next_helpdesk_archive_partition,
        cleanup_helpdesk_attachments_task,
        send_helpdesk_digest,
    ]
    cron_jobs = [
        cron(
            "app.worker.tasks.audit.flush_audit_queue",
            second=set(range(0, 60, 5)),
            run_at_startup=True,
        ),
        cron(
            "app.worker.tasks.audit.create_next_audit_partition",
            month=None,
            day=1,
            hour=2,
            minute=0,
            second=0,
            run_at_startup=True,
        ),
        cron(
            "app.worker.tasks.audit.drop_old_audit_partitions",
            month=None,
            day=1,
            hour=3,
            minute=0,
            second=0,
        ),
        cron(
            "app.worker.tasks.news.publish_scheduled_news",
            minute=None,
            second=0,
        ),
        cron(
            "app.worker.tasks.news.close_expired_polls",
            minute=None,
            second=15,
        ),
        cron(
            "app.worker.tasks.news.archive_expired_news",
            minute=0,
            second=30,
        ),
        cron(
            "app.worker.tasks.news.sync_users_from_keycloak",
            minute=0,
            second=0,
        ),
        cron(
            "app.worker.tasks.photos.cleanup_deleted_photos",
            hour=4,
            minute=0,
            second=0,
        ),
        cron(
            "app.worker.tasks.photos.cleanup_zip_jobs",
            hour=5,
            minute=0,
            second=0,
        ),
        cron(
            "app.worker.tasks.photos.detect_missing_thumbnails",
            minute=set(range(0, 60, 5)),
            second=0,
        ),
        cron(
            "app.worker.tasks.metrics.refresh_custom_metrics",
            second={0, 30},
            run_at_startup=True,
        ),
        cron(
            "app.worker.tasks.audit.cleanup_idempotency_keys",
            hour=3,
            minute=30,
            second=0,
        ),
        cron(
            "app.worker.tasks.metrics.worker_heartbeat",
            second={0, 30},
            run_at_startup=True,
        ),
        cron(
            "app.worker.tasks.email_outbox.process_email_outbox",
            second={0, 10, 20, 30, 40, 50},
            run_at_startup=True,
        ),
        cron(
            "app.worker.tasks.email_outbox.cleanup_email_outbox",
            hour=4,
            minute=15,
            second=0,
        ),
        cron(
            "app.worker.tasks.kb.purge_kb_trash",
            hour=4,
            minute=30,
            second=0,
        ),
        cron(
            "app.worker.tasks.kb.cleanup_kb_orphan_dirs",
            hour=4,
            minute=45,
            second=0,
        ),
        # ── Helpdesk ────────────────────────────────────────────────────────
        # IMAP poll: статически каждые 30 c; реальный интервал — из
        # helpdesk_mailbox_settings.poll_interval_seconds (interval guard внутри).
        cron(
            "app.worker.tasks.helpdesk.poll_helpdesk_mailbox",
            second={0, 30},
        ),
        cron(
            "app.worker.tasks.helpdesk.archive_closed_tickets_task",
            hour=3,
            minute=20,
            second=0,
        ),
        cron(
            "app.worker.tasks.helpdesk.create_next_helpdesk_archive_partition",
            month=None,
            day=1,
            hour=2,
            minute=0,
            second=0,
            run_at_startup=True,
        ),
        cron(
            "app.worker.tasks.helpdesk.cleanup_helpdesk_attachments_task",
            hour=4,
            minute=0,
            second=0,
        ),
        # Daily digest: cron ежечасно; реальное время — из
        # helpdesk_digest_settings (interval guard внутри).
        cron(
            "app.worker.tasks.helpdesk.send_helpdesk_digest",
            minute=0,
            second=0,
        ),
    ]
