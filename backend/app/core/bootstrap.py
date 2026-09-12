from datetime import UTC, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.user import User

logger = get_logger(__name__)

_BOOTSTRAP_LOCK_KEY = 0x504F5254414C0001  # stable int64 — 'PORTAL\x00\x01'


async def bootstrap_admin() -> None:
    """При запуске создаёт первого локального admin, если заданы ADMIN_EMAIL + ADMIN_PASSWORD.

    Защищён транзакционным pg_advisory_xact_lock: конкурентные воркеры
    сериализуются — первый создаёт админа, остальные видят его и выходят.
    """
    from app.core.config import get_settings

    settings = get_settings()

    if not settings.admin_email or not settings.admin_password:
        return
    if not settings.local_auth_enabled:
        return

    async with AsyncSessionLocal() as db:
        # Транзакционный advisory-lock: освобождается автоматически при
        # коммите/откате ТОЙ ЖЕ транзакции. Прежний вариант (session-level
        # pg_try_advisory_lock + unlock в finally) протекал: после commit
        # сессия возвращает соединение в пул, unlock из finally мог попасть
        # на ДРУГОЕ соединение — лок оставался held на утёкшем соединении,
        # и все последующие bootstrap в процессе молча выходили по
        # try_lock=False (админ не создавался; флейк TestBootstrapAdmin,
        # 2026-08-28).
        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _BOOTSTRAP_LOCK_KEY})

        existing_result = await db.execute(
            select(User).where(func.lower(User.email) == settings.admin_email.lower())
        )
        existing_user = existing_result.scalar_one_or_none()
        if existing_user is not None:
            # Безопасное поведение: роль и auth_source синхронизируем, но
            # password_hash НЕ перезаписываем при каждом старте, иначе пароль
            # сменённый через UI откатывается к значению ADMIN_PASSWORD.
            values = {"role": "admin", "auth_source": "local"}
            reason = "bootstrap.admin_role_synced"
            if settings.admin_password_reset_on_start or not existing_user.password_hash:
                values["password_hash"] = hash_password(settings.admin_password)
                reason = "bootstrap.admin_password_synced"
                if settings.admin_password_reset_on_start:
                    logger.warning(
                        "bootstrap.admin_password_reset_on_start_enabled",
                        user_email=settings.admin_email,
                        note="Disable ADMIN_PASSWORD_RESET_ON_START after first login",
                    )
            await db.execute(
                update(User)
                .where(func.lower(User.email) == settings.admin_email.lower())
                .values(**values)
            )
            await db.commit()
            logger.info(reason, user_email=settings.admin_email)
            return

        # limit(1) обязателен: админов может быть несколько (роль выдаётся
        # через admin-API), scalar_one_or_none без лимита падал бы
        # MultipleResultsFound и ронял старт приложения (нашлось на
        # integration-прогоне 2026-08-28).
        result = await db.execute(select(User.id).where(User.role == "admin").limit(1))
        if result.scalar_one_or_none():
            await db.commit()
            return

        now = datetime.now(UTC)
        stmt = (
            pg_insert(User)
            .values(
                email=settings.admin_email,
                full_name="Administrator",
                auth_source="local",
                password_hash=hash_password(settings.admin_password),
                role="admin",
                updated_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=[func.lower(User.email)],
                index_where=User.deleted_at.is_(None),
            )
        )
        await db.execute(stmt)
        await db.commit()
        logger.info("bootstrap.admin_created", user_email=settings.admin_email)
