"""user_attribute_mappings table

Revision ID: 026
Revises: 025
Create Date: 2026-05-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_attribute_mappings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("attr_key", sa.String(255), nullable=False),
        sa.Column("label_ru", sa.String(255), nullable=False),
        sa.Column("label_en", sa.String(255), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("attr_key", name="uq_user_attribute_mappings_attr_key"),
    )
    op.create_index(
        "idx_user_attribute_mappings_sort",
        "user_attribute_mappings",
        ["sort_order"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_attribute_mappings_sort", table_name="user_attribute_mappings")
    op.drop_table("user_attribute_mappings")
