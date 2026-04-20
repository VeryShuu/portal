from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(__name__)


async def startup(ctx: dict) -> None:
    logger.info("arq_worker.startup")


async def shutdown(ctx: dict) -> None:
    logger.info("arq_worker.shutdown")


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.arq_max_jobs
    on_startup = startup
    on_shutdown = shutdown
    functions: list = []
    cron_jobs: list = [
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
    ]
