"""news: replace category (str) with categories (array)

Revision ID: 029
Revises: 028
Create Date: 2026-05-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "news",
        sa.Column(
            "categories",
            ARRAY(sa.String(100)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(
        "UPDATE news SET categories = ARRAY[category] WHERE category IS NOT NULL AND category <> ''"
    )
    op.drop_column("news", "category")


def downgrade() -> None:
    op.add_column("news", sa.Column("category", sa.String(100), nullable=True))
    op.execute(
        "UPDATE news SET category = categories[1] WHERE array_length(categories, 1) > 0"
    )
    op.drop_column("news", "categories")
