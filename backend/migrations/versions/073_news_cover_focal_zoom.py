"""news cover focal zoom

Revision ID: 073
Revises: 072
Create Date: 2026-06-18

Adds ``news.cover_focal_zoom`` (SMALLINT, percent 100..300, NULL = 100 = no
zoom). Combined with ``cover_focal_x`` / ``cover_focal_y`` it drives a pure
client-side CSS ``transform: scale()`` around the focal point — the cover image
and its WebP/AVIF variants are not regenerated.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "073"
down_revision: str | None = "072"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("news", sa.Column("cover_focal_zoom", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        "ck_news_cover_focal_zoom_range",
        "news",
        "cover_focal_zoom IS NULL OR (cover_focal_zoom BETWEEN 100 AND 300)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_news_cover_focal_zoom_range", "news", type_="check")
    op.drop_column("news", "cover_focal_zoom")
