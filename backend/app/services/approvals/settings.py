"""Singleton настроек подключения к ERP (таблица ``approvals_settings``).

Клон паттерна directum: строка ``id=1`` сеется миграцией (115), пароль
хранится Fernet-шифром (``auth_password_enc``), plaintext — только в памяти
на время вызова 1С.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secret_crypto import decrypt_secret
from app.models.approvals import ApprovalsSettings


async def load_approvals_settings(db: AsyncSession) -> ApprovalsSettings | None:
    """Singleton всегда существует (миграция 115 INSERT id=1); защитно None."""
    return (await db.scalars(select(ApprovalsSettings).where(ApprovalsSettings.id == 1))).first()


def is_configured(row: ApprovalsSettings | None) -> bool:
    """Подключение настроено: URL + учётка + пароль. Иначе модуль отвечает
    503 «не настроен» (не 500) — пользователь понимает, куда бежать."""
    return bool(row and row.base_url and row.auth_username and row.auth_password_enc)


def decrypt_password(row: ApprovalsSettings) -> str | None:
    if not row.auth_password_enc:
        return None
    try:
        return decrypt_secret(row.auth_password_enc)
    except Exception:
        return None
