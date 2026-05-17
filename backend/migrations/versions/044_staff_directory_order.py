"""staff directory: custom order + hidden flag

Revision ID: 044
Revises: 043
Create Date: 2026-05-15

Adds:
- users.staff_sort_order (INTEGER, nullable) — позиция пользователя внутри
  отдела в справочнике сотрудников. NULL = в конец (алфавитно).
- users.staff_hidden (BOOLEAN, default false) — скрыть пользователя из
  /staff (но оставить видимым в остальных местах: /users/:id, поиск, и т.д.).
- staff_department_orders (department TEXT PK, sort_order INTEGER) — порядок
  отделов в справочнике. Отделы без записи показываются в конце алфавитно.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("staff_sort_order", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "staff_hidden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "idx_users_staff_sort_order",
        "users",
        ["department", "staff_sort_order"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "staff_department_orders",
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("department", name="pk_staff_department_orders"),
    )


def downgrade() -> None:
    op.drop_table("staff_department_orders")
    op.drop_index("idx_users_staff_sort_order", table_name="users")
    op.drop_column("users", "staff_hidden")
    op.drop_column("users", "staff_sort_order")
