"""approvals: token_base_url — отдельный базовый URL выдачи токенов 1С

Revision ID: 116
Revises: 115
Create Date: 2026-09-05

1С вынесла выдачу токенов на отдельный RootURL публикации:
``…/hs/PortalAuth/GETTokenByLogin`` (методы документов остаются на
``…/hs/Auth/...``). Плюс безопасности: на ``/PortalAuth/*`` право есть только
у учётки Portal. Колонка ``approvals_settings.token_base_url`` nullable:
NULL/пусто = как ``base_url`` (обратная совместимость), клиент делает
COALESCE-логику на своей стороне.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "116"
down_revision: str | None = "115"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # nosec B608 — статический DDL без интерполяции.
    op.execute(
        text("ALTER TABLE approvals_settings ADD COLUMN IF NOT EXISTS token_base_url VARCHAR(255)")
    )


def downgrade() -> None:
    op.execute(text("ALTER TABLE approvals_settings DROP COLUMN IF EXISTS token_base_url"))
