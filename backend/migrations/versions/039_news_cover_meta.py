"""news cover dominant color and variants

Revision ID: 039
Revises: 038
Create Date: 2026-05-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "news",
        sa.Column("cover_dominant_color", sa.String(length=7), nullable=True),
    )
    op.add_column(
        "news",
        sa.Column("cover_variants", sa.ARRAY(sa.Integer()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("news", "cover_variants")
    op.drop_column("news", "cover_dominant_color")
