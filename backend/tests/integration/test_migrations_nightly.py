"""Nightly smoke: run alembic upgrade head on a fresh PG container.

The main migration tests (``test_migrations.py``) reuse a shared
PostgreSQL instance for speed. This nightly suite spins up a clean
``portal-postgres:16`` via testcontainers and validates that the full
migration stack lands cleanly on an empty cluster (catches issues that
only manifest when the bootstrap order is exercised from scratch).
"""

from __future__ import annotations

import os

import pytest

testcontainers = pytest.importorskip("testcontainers.postgres")
PostgresContainer = testcontainers.PostgresContainer  # type: ignore[attr-defined]

pytestmark = [
    pytest.mark.nightly,
    pytest.mark.skipif(
        os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"),
        reason="INTEGRATION_DB=true required",
    ),
    pytest.mark.skipif(
        os.environ.get("NIGHTLY", "false").lower() not in ("1", "true", "yes"),
        reason="NIGHTLY=true required",
    ),
]


POSTGRES_IMAGE = "portal-postgres:16"


def test_alembic_upgrade_head_on_clean_container():
    from alembic import command
    from alembic.config import Config

    with PostgresContainer(POSTGRES_IMAGE) as container:
        url = container.get_connection_url()
        plain_url = url.replace("postgresql+psycopg2://", "postgresql://").replace("+psycopg2", "")
        asyncpg_url = plain_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # init.sql НЕ выполняем вручную: образ portal-postgres:16 применяет его
        # автоматически при первом старте (запечён в /docker-entrypoint-initdb.d/,
        # см. ADR-046). Ручное выполнение упало бы с duplicate key (FTS-конфиг
        # уже создан).
        cfg = Config()
        cfg.set_main_option("script_location", "migrations")
        cfg.set_main_option("sqlalchemy.url", asyncpg_url)
        command.upgrade(cfg, "head")
