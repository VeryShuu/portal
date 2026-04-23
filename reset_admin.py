import asyncio
import os
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://portal:change_me_strong_password@localhost:5432/portal")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@company.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change_me_admin_password")

async def reset():
    import sys
    sys.path.insert(0, "/app")
    from app.core.security import hash_password
    from app.models.user import User

    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    new_hash = hash_password(ADMIN_PASSWORD)
    print(f"Resetting password for {ADMIN_EMAIL}")
    print(f"New hash: {new_hash[:20]}...")

    async with async_session() as db:
        await db.execute(
            update(User)
            .where(User.email == ADMIN_EMAIL)
            .values(password_hash=new_hash, auth_source="local")
        )
        await db.commit()
        print("Done!")

asyncio.run(reset())
