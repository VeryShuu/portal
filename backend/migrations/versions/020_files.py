"""files module: portal-managed folder tree + per-folder ACL for Nextcloud storage

Revision ID: 020
Revises: 019
Create Date: 2026-04-26

Architecture (ADR-032):
  All file operations go through service account 'portal-svc' in Nextcloud.
  Portal maintains a shadow folder tree (file_folders) with its own ACL table.
  Nextcloud is used as dumb storage; permissions are enforced on portal side.

NOTE: Phase 5 (Nextcloud files) is implemented but module can be disabled
via /admin/modules. The tables file_folders/file_folder_permissions are
created unconditionally because module-toggle only affects API endpoints.
See docs/adr.md (ADR-032) and docs/api-contracts.md (§3.6).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "file_folders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("file_folders.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column(
            "nc_path",
            sa.String(2000),
            nullable=False,
            unique=True,
            comment="Path relative to portal-svc WebDAV root (e.g. PortalFiles/HR/Docs)",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_file_folders_parent", "file_folders", ["parent_id"])
    op.create_index("idx_file_folders_nc_path", "file_folders", ["nc_path"])
    op.create_index(
        "idx_file_folders_active",
        "file_folders",
        ["parent_id", "name"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "file_folder_permissions",
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
        sa.Column("subject_type", sa.String(10), nullable=False),
        sa.Column("subject_id", sa.String(255), nullable=False),
        sa.Column("subject_name", sa.String(255), nullable=False),
        sa.Column("permission", sa.String(20), nullable=False),
        sa.Column(
            "granted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "subject_type IN ('user', 'group')",
            name="ck_file_folder_perm_subject_type",
        ),
        sa.CheckConstraint(
            "permission IN ('viewer', 'editor', 'manager')",
            name="ck_file_folder_perm_permission",
        ),
        sa.UniqueConstraint(
            "folder_id",
            "subject_id",
            name="uq_file_folder_perm_folder_subject",
        ),
    )
    op.create_index("idx_file_folder_perm_folder", "file_folder_permissions", ["folder_id"])
    op.create_index("idx_file_folder_perm_subject", "file_folder_permissions", ["subject_id"])


def downgrade() -> None:
    op.drop_table("file_folder_permissions")
    op.drop_table("file_folders")
