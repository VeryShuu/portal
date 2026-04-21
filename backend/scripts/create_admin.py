import asyncio
import sys
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.core.database import AsyncSessionLocal as async_session_factory
from app.core.security import hash_password
from app.models.user import User

EMAIL = sys.argv[1] if len(sys.argv) > 1 else "admin@company.local"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "change_me_admin_password"

async def create_admin():
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == EMAIL))
        if result.scalar_one_or_none():
            print(f"User {EMAIL} already exists")
            return
        now = datetime.now(UTC)
        stmt = pg_insert(User).values(
            email=EMAIL,
            full_name="Administrator",
            auth_source="local",
            password_hash=hash_password(PASSWORD),
            role="admin",
            updated_at=now,
        ).on_conflict_do_nothing(index_elements=["email"])
        await db.execute(stmt)
        await db.commit()
        print(f"Admin created: {EMAIL}")

asyncio.run(create_admin())
