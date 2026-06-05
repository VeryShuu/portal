"""directory entries: bind an internal /files folder, drop avatar & external folder url

Replaces the free-form external ``folder_url`` with an internal ``folder_id``
referencing ``file_folders`` (ON DELETE SET NULL) and removes the per-entry
avatar feature entirely (``avatar_path`` column + ``/data/directory_avatars``).

Revision ID: 065
Revises: 064
Create Date: 2026-06-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "065"
down_revision: str | None = "064"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "object_directory_entries",
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_ode_folder",
        "object_directory_entries",
        "file_folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_ode_folder", "object_directory_entries", ["folder_id"])

    op.drop_column("object_directory_entries", "avatar_path")
    op.drop_column("object_directory_entries", "folder_url")


def downgrade() -> None:
    op.add_column(
        "object_directory_entries",
        sa.Column("folder_url", sa.String(2048), nullable=True),
    )
    op.add_column(
        "object_directory_entries",
        sa.Column("avatar_path", sa.String(500), nullable=True),
    )
    op.drop_index("idx_ode_folder", table_name="object_directory_entries")
    op.drop_constraint("fk_ode_folder", "object_directory_entries", type_="foreignkey")
    op.drop_column("object_directory_entries", "folder_id")
