"""service_links: show_on_home flag

Revision ID: 070
Revises: 069
Create Date: 2026-06-15

Adds the ``service_links.show_on_home`` boolean flag (default ``false``) that
controls which corporate links are featured in the home-page quick-services
widget. Safe for existing rows via ``server_default='false'``.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "070"
down_revision: str | None = "069"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "service_links",
        sa.Column(
            "show_on_home",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("service_links", "show_on_home")
