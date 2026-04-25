from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)

settings = get_settings()
configure_logging(
    environment=settings.environment,
    log_level=settings.log_level,
    service_name="portal-worker",
    force_json=settings.log_force_json,
)
logger = get_logger(__name__)


async def startup(ctx: dict) -> None:
    logger.info("arq_worker.startup")


async def shutdown(ctx: dict) -> None:
    logger.info("arq_worker.shutdown")


async def on_job_start(ctx: dict) -> None:
    """Биндит job_id / job_try / function_name в contextvars для всех логов задачи."""
    clear_request_context()
    bind_request_context(
        job_id=ctx.get("job_id"),
        job_try=ctx.get("job_try"),
        function=ctx.get("enqueue_time") and ctx.get("function") or None,
        correlation_id=ctx.get("job_id"),  # job_id выступает correlation_id
    )


async def on_job_end(ctx: dict) -> None:
    clear_request_context()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.arq_max_jobs
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    on_job_end = on_job_end
    functions = [
        "app.worker.tasks.news.sync_users_from_keycloak",
        "app.worker.tasks.notifications.send_email_notification",
        "app.worker.tasks.notifications.notify_news_published",
        "app.worker.tasks.notifications.notify_suggestion_reviewed_email",
        "app.worker.tasks.photos.process_photo_upload",
        "app.worker.tasks.photos.cleanup_deleted_photos",
        "app.worker.tasks.photos.generate_folder_zip",
        "app.worker.tasks.photos.cleanup_zip_jobs",
        "app.worker.tasks.photos.detect_missing_thumbnails",
    ]
    cron_jobs = [
        cron(
            "app.worker.tasks.audit.flush_audit_queue",
            second={0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30,
                    32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58},
            run_at_startup=True,
        ),
        cron(
            "app.worker.tasks.audit.create_next_audit_partition",
            month=None,
            day=1,
            hour=2,
            minute=0,
            second=0,
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
            minute={0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
                    16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
                    31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45,
                    46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59},
            second=0,
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
            hour=5,
            minute=30,
            second=0,
        ),
    ]
