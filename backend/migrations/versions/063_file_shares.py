"""file_shares — per-file shares for the Nextcloud file module (sharing.md)

Revision ID: 063
Revises: 062
Create Date: 2026-05-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "063"
down_revision: str | None = "062"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "file_shares",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("file_folders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("nc_path", sa.String(2000), nullable=False),
        sa.Column("subject_type", sa.String(10), nullable=False),
        sa.Column("subject_id", sa.String(255), nullable=False),
        sa.Column("subject_name", sa.String(255), nullable=False),
        sa.Column("permission", sa.String(20), nullable=False),
        sa.Column(
            "shared_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "subject_type IN ('user', 'group')",
            name="ck_file_share_subject_type",
        ),
        sa.CheckConstraint(
            "permission IN ('viewer', 'editor')",
            name="ck_file_share_permission",
        ),
        sa.UniqueConstraint(
            "folder_id", "filename", "subject_id", name="uq_file_share_folder_file_subject"
        ),
    )

    op.create_index(
        "idx_file_shares_folder_filename",
        "file_shares",
        ["folder_id", "filename"],
    )
    op.create_index("idx_file_shares_subject_id", "file_shares", ["subject_id"])
    op.create_index(
        "idx_file_shares_subject_active",
        "file_shares",
        ["subject_id", "revoked_at"],
    )
    op.create_index("idx_file_shares_expires_at", "file_shares", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_file_shares_expires_at", table_name="file_shares")
    op.drop_index("idx_file_shares_subject_active", table_name="file_shares")
    op.drop_index("idx_file_shares_subject_id", table_name="file_shares")
    op.drop_index("idx_file_shares_folder_filename", table_name="file_shares")
    op.drop_table("file_shares")
