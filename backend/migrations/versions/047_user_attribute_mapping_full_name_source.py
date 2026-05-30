"""Add is_full_name_source flag to user_attribute_mappings

Revision ID: 047
Revises: 046
Create Date: 2026-05-17

Allows administrators to mark one Keycloak attribute mapping as the source
of the canonical ``users.full_name`` column.  Used by the Keycloak sync
worker to overwrite the (firstName + lastName)-derived value with a
free-form attribute (typical case: AD ``cn`` holding full FIO with
patronymic).

A partial unique index guarantees at most one mapping can carry the flag
at any moment, so the worker logic can read it unambiguously without an
ORDER BY tiebreaker.
"""

from alembic import op
import sqlalchemy as sa

revision: str = "047"
down_revision: str | None = "046"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "user_attribute_mappings",
        sa.Column(
            "is_full_name_source",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_attribute_mappings_full_name_source "
        "ON user_attribute_mappings (is_full_name_source) "
        "WHERE is_full_name_source = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_user_attribute_mappings_full_name_source")
    op.drop_column("user_attribute_mappings", "is_full_name_source")
