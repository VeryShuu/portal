"""photo_folders: add storage_kind/storage_root

Revision ID: 057
Revises: 056
Create Date: 2026-05-22
"""

import sqlalchemy as sa
from alembic import op

revision: str = "057"
down_revision: str | None = "056"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "photo_folders",
        sa.Column(
            "storage_kind",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'originals'"),
        ),
    )
    op.add_column(
        "photo_folders",
        sa.Column("storage_root", sa.String(length=500), nullable=True),
    )
    op.create_check_constraint(
        "ck_photo_folders_storage_kind",
        "photo_folders",
        "storage_kind IN ('originals', 'import')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_photo_folders_storage_kind", "photo_folders", type_="check")
    op.drop_column("photo_folders", "storage_root")
    op.drop_column("photo_folders", "storage_kind")
