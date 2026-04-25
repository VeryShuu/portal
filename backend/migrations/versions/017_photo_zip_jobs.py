"""photo_zip_jobs — задания на генерацию ZIP-архивов папок

Revision ID: 017
Revises: 016
Create Date: 2026-04-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photo_zip_jobs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("folder_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["folder_id"], ["photo_folders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_photo_zip_jobs_folder", "photo_zip_jobs", ["folder_id"])
    op.create_index("idx_photo_zip_jobs_user", "photo_zip_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_photo_zip_jobs_user", table_name="photo_zip_jobs")
    op.drop_index("idx_photo_zip_jobs_folder", table_name="photo_zip_jobs")
    op.drop_table("photo_zip_jobs")
