"""Auto-mark security/ tests with the `security` marker.

Также определяет `security_authed_client_factory` — фикстуру, специально
предназначенную для security-тестов (authz/HTTP-уровень без бизнес-логики).
Использует no-op заглушку `get_db`, которая отдаёт пустые результаты,
поэтому НЕ ПОДХОДИТ для unit/integration-тестов, проверяющих бизнес-сценарии.
"""

from __future__ import annotations

import pytest
import pytest_asyncio


def pytest_collection_modifyitems(config, items):
    marker = pytest.mark.security
    for item in items:
        item.add_marker(marker)


@pytest_asyncio.fixture
async def security_authed_client_factory(authed_client_factory):
    """Алиас для authed_client_factory, рекомендованный к использованию
    только из tests/security/. Сигналит читателю, что _fake_db (no-op) внутри
    осознанно: проверяем authz/headers/CSRF, а не данные.

    Бизнес-сценарии (CRUD/relationships/SQL) должны использовать
    integration-фикстуру `real_db_session` (tests/integration/conftest.py).
    """
    return authed_client_factory
