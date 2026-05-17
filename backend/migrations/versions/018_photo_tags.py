"""photo_tags — теги фотографий

Revision ID: 018
Revises: 017
Create Date: 2026-04-25
"""

from __future__ import annotations


import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "photo_tags",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_photo_tags_name"),
        sa.UniqueConstraint("slug", name="uq_photo_tags_slug"),
    )
    op.create_table(
        "photo_tag_assignments",
        sa.Column("photo_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["photo_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("photo_id", "tag_id"),
    )
    op.create_index("idx_pta_photo", "photo_tag_assignments", ["photo_id"])
    op.create_index("idx_pta_tag", "photo_tag_assignments", ["tag_id"])


def downgrade() -> None:
    op.drop_index("idx_pta_tag", table_name="photo_tag_assignments")
    op.drop_index("idx_pta_photo", table_name="photo_tag_assignments")
    op.drop_table("photo_tag_assignments")
    op.drop_table("photo_tags")
