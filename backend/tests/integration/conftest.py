"""Фикстуры исключительно для integration-тестов.

Все тесты в этом каталоге автоматически помечаются маркером `integration`
и пропускаются если не задан INTEGRATION_DB=true (или INTEGRATION_REDIS=true).

`real_db_session` / `real_user` / `real_editor` / `real_admin` вынесены
в `tests/db_fixtures.py`, чтобы их можно было переиспользовать из `tests/unit/`
для тестов с маркером `@pytest.mark.unit_with_db` (REVIEW-2.1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# `real_db_session` / `real_user` / `real_editor` / `real_admin` живут
# в `tests/db_fixtures.py` и подключены через корневой `tests/conftest.py` —
# доступны как здесь, так и в `tests/unit/` (для маркера `@pytest.mark.unit_with_db`).

# Каталог этого conftest — маркер ставится ТОЛЬКО его жителям (audit-review
# 2026-08-22, P1: раньше хук маркировал всю собранную коллекцию, и
# `pytest -m integration` выбирал заодно 4722 unit-теста).
_THIS_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(config, items):
    """Авто-маркировка integration — только тестам из tests/integration/."""
    integration_marker = pytest.mark.integration
    for item in items:
        if _THIS_DIR in item.path.parents:
            item.add_marker(integration_marker)
