"""users.email: case-insensitive unique index

Replace case-sensitive UniqueConstraint on email with a functional unique index
on LOWER(email) scoped to active (non-deleted) users only.

This prevents duplicate accounts like User1@x.ru and user1@x.ru and allows
the same email to be reused after soft-delete.

Revision ID: 030
Revises: 029
Create Date: 2026-05-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")

    op.drop_index("idx_users_email", table_name="users")

    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX idx_users_email_ci"
            " ON users (LOWER(email))"
            " WHERE deleted_at IS NULL"
        )
    )

    op.execute(
        sa.text(
            "CREATE INDEX idx_users_email_lower"
            " ON users (LOWER(email))"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_users_email_ci"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_users_email_lower"))

    op.create_index("idx_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_email", "users", ["email"])
