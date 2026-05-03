import asyncio
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://test:test@localhost/test'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
os.environ['SECRET_KEY'] = 'test_secret_key_that_is_32_chars_long_ok'
os.environ['KEYCLOAK_URL'] = 'http://keycloak:8080'
os.environ['KEYCLOAK_CLIENT_SECRET'] = 'test_secret'
os.environ['ENVIRONMENT'] = 'development'
os.environ['LOCAL_AUTH_ENABLED'] = 'true'
os.environ['ADMIN_EMAIL'] = ''
os.environ['ADMIN_PASSWORD'] = ''
os.environ['PORTAL_BASE_URL'] = 'http://test'

async def main():
    from fastapi_limiter.depends import RateLimiter
    async def noop(self, request, response):
        return None
    RateLimiter.__call__ = noop

    import app.main as main_mod
    import importlib
    importlib.reload(main_mod)

    import fakeredis.aioredis as fakeredis_aio
    main_mod.app.state.redis = fakeredis_aio.FakeRedis(decode_responses=True)

    from unittest.mock import AsyncMock, MagicMock
    from app.api.deps import get_current_user, get_db
    import uuid
    from datetime import UTC, datetime
    from types import SimpleNamespace

    user = SimpleNamespace(
        id=uuid.uuid4(), email='reader@test.com', full_name='Reader',
        department='IT', position='Engineer', phone=None, role='reader',
        auth_source='local', password_hash=None, avatar_url=None,
        presence_status='office', notify_email=True, notify_inapp=True,
        lang='ru', preferences={}, created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC), last_login_at=None
    )

    async def fake_user():
        return user

    async def fake_db():
        session = MagicMock()
        result = MagicMock()
        result.scalar_one = MagicMock(return_value=0)
        result.scalar_one_or_none = MagicMock(return_value=None)
        result.scalars = MagicMock(return_value=MagicMock(
            all=MagicMock(return_value=[]), first=MagicMock(return_value=None)
        ))
        result.all = MagicMock(return_value=[])
        result.first = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        yield session

    main_mod.app.dependency_overrides[get_current_user] = fake_user
    main_mod.app.dependency_overrides[get_db] = fake_db

    from unittest.mock import patch, AsyncMock as AM
    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app),
        base_url='http://test',
        headers={'Origin': 'http://test', 'x-xsrf-token': 'tok'},
        cookies={'XSRF-TOKEN': 'tok'}
    ) as ac:
        with patch('app.api.search.filter_accessible_articles', new_callable=AM, return_value=[]):
            r = await ac.get('/api/v1/search?q=hello')
        print('Status:', r.status_code)
        print('Body:', r.text[:2000])

asyncio.run(main())
