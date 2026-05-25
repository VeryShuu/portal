import asyncio

import asyncpg
from arq import cron, func
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)
from app.worker.tasks.audit import cleanup_idempotency_keys
from app.worker.tasks.email_outbox import cleanup_email_outbox, process_email_outbox
from app.worker.tasks.files import _SYNC_LOCK_KEY, startup_sync_nc_folders
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
    notify_suggestion_reviewed_email,
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
    pool = ctx.get("pg_pool")
    if pool is not None:
        await pool.close()
    redis = ctx.get("redis")
    if redis is not None:
        await redis.delete(_SYNC_LOCK_KEY)
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
        notify_suggestion_reviewed_email,
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
    ]
