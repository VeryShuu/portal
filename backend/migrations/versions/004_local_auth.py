"""Add local authentication fields to users table

Revision ID: 004
Revises: 003
Create Date: 2026-04-20
"""

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.alter_column("users", "keycloak_id", nullable=True)

    op.add_column(
        "users",
        sa.Column(
            "auth_source",
            sa.String(20),
            nullable=False,
            server_default="keycloak",
        ),
    )
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(255), nullable=True),
    )

    op.create_check_constraint(
        "ck_users_auth_source",
        "users",
        "auth_source IN ('keycloak', 'local')",
    )
    op.create_index("idx_users_auth_source", "users", ["auth_source"])


def downgrade() -> None:
    op.drop_index("idx_users_auth_source", table_name="users")
    op.drop_constraint("ck_users_auth_source", "users", type_="check")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "auth_source")
    op.alter_column("users", "keycloak_id", nullable=False)
