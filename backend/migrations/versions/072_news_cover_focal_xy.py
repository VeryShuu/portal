"""news: cover focal point as x/y percentages

Revision ID: 072
Revises: 071
Create Date: 2026-06-18

Replaces the enum-style ``news.cover_focal_point`` (top/center/bottom) with two
integer percentage columns ``cover_focal_x`` / ``cover_focal_y`` (0..100, NULL =
center). The legacy enum is backfilled into x/y and then dropped.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "072"
down_revision: str | None = "071"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("news", sa.Column("cover_focal_x", sa.SmallInteger(), nullable=True))
    op.add_column("news", sa.Column("cover_focal_y", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        "ck_news_cover_focal_x_range",
        "news",
        "cover_focal_x IS NULL OR (cover_focal_x BETWEEN 0 AND 100)",
    )
    op.create_check_constraint(
        "ck_news_cover_focal_y_range",
        "news",
        "cover_focal_y IS NULL OR (cover_focal_y BETWEEN 0 AND 100)",
    )
    # Backfill from the legacy enum: top -> (50, 0), bottom -> (50, 100).
    # center / NULL stay NULL (interpreted as 50/50 by the app).
    op.execute(
        "UPDATE news SET cover_focal_x = 50, cover_focal_y = 0 "
        "WHERE cover_focal_point = 'top'"
    )
    op.execute(
        "UPDATE news SET cover_focal_x = 50, cover_focal_y = 100 "
        "WHERE cover_focal_point = 'bottom'"
    )
    op.drop_column("news", "cover_focal_point")


def downgrade() -> None:
    op.add_column("news", sa.Column("cover_focal_point", sa.String(length=16), nullable=True))
    # Reconstruct the coarse enum from x/y: y<=25 -> top, y>=75 -> bottom, else center.
    op.execute("UPDATE news SET cover_focal_point = 'top' WHERE cover_focal_y <= 25")
    op.execute("UPDATE news SET cover_focal_point = 'bottom' WHERE cover_focal_y >= 75")
    op.execute(
        "UPDATE news SET cover_focal_point = 'center' "
        "WHERE cover_focal_y IS NOT NULL AND cover_focal_y > 25 AND cover_focal_y < 75"
    )
    op.drop_constraint("ck_news_cover_focal_y_range", "news", type_="check")
    op.drop_constraint("ck_news_cover_focal_x_range", "news", type_="check")
    op.drop_column("news", "cover_focal_y")
    op.drop_column("news", "cover_focal_x")
