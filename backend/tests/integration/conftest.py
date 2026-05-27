"""Фикстуры исключительно для integration-тестов.

Все тесты в этом каталоге автоматически помечаются маркером `integration`
и пропускаются если не задан INTEGRATION_DB=true (или INTEGRATION_REDIS=true).

`real_db_session` / `real_user` / `real_editor` / `real_admin` вынесены
в `tests/db_fixtures.py`, чтобы их можно было переиспользовать из `tests/unit/`
для тестов с маркером `@pytest.mark.unit_with_db` (REVIEW-2.1).
"""

from __future__ import annotations

import pytest

# `real_db_session` / `real_user` / `real_editor` / `real_admin` живут
# в `tests/db_fixtures.py` и подключаются через корневой `tests/conftest.py` —
# доступны как здесь, так и в `tests/unit/` (для маркера `@pytest.mark.unit_with_db`).


def pytest_collection_modifyitems(config, items):
    """Авто-маркировка integration."""
    integration_marker = pytest.mark.integration
    for item in items:
        item.add_marker(integration_marker)
