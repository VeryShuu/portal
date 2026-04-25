"""photo_folder_share_tokens — публичные ссылки на папки

Revision ID: 019
Revises: 018
Create Date: 2026-04-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photo_folder_share_tokens",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("folder_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["folder_id"], ["photo_folders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_pfst_token"),
    )
    op.create_index("idx_pfst_folder", "photo_folder_share_tokens", ["folder_id"])
    op.create_index("idx_pfst_created_by", "photo_folder_share_tokens", ["created_by"])


def downgrade() -> None:
    op.drop_index("idx_pfst_created_by", table_name="photo_folder_share_tokens")
    op.drop_index("idx_pfst_folder", table_name="photo_folder_share_tokens")
    op.drop_table("photo_folder_share_tokens")
