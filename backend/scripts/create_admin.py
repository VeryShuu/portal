"""CLI для ручного создания локального admin.

Пароль читается ТОЛЬКО из переменной окружения ADMIN_PASSWORD (или
интерактивного ввода через getpass), чтобы не светиться в `ps aux` и
истории shell. Email можно передать через ADMIN_EMAIL или первым
аргументом.

Примеры:
    ADMIN_EMAIL=admin@company.local ADMIN_PASSWORD='...' \
        python -m scripts.create_admin
    python -m scripts.create_admin admin@company.local   # запросит пароль
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal as async_session_factory
from app.core.security import hash_password
from app.models.user import User


def _resolve_email() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    return os.environ.get("ADMIN_EMAIL") or "admin@company.local"


def _resolve_password() -> str:
    pwd = os.environ.get("ADMIN_PASSWORD")
    if pwd:
        return pwd
    if not sys.stdin.isatty():
        raise SystemExit(
            "Password required: set ADMIN_PASSWORD env var or run interactively"
        )
    pwd = getpass.getpass("Admin password: ")
    if not pwd or len(pwd) < 8:
        raise SystemExit("Password must be at least 8 chars")
    return pwd


async def create_admin(email: str, password: str) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"User {email} already exists")
            return
        now = datetime.now(UTC)
        stmt = pg_insert(User).values(
            email=email,
            full_name="Administrator",
            auth_source="local",
            password_hash=hash_password(password),
            role="admin",
            updated_at=now,
        ).on_conflict_do_nothing(index_elements=["email"])
        await db.execute(stmt)
        await db.commit()
        print(f"Admin created: {email}")


if __name__ == "__main__":
    asyncio.run(create_admin(_resolve_email(), _resolve_password()))
