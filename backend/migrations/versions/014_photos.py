"""photos module: folders, permissions, photos

Revision ID: 014
Revises: 013
Create Date: 2026-04-24
"""


import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "photo_folders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("photo_folders.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("path", sa.String(2000), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_photo_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint("parent_id", "slug", name="uq_photo_folders_parent_slug"),
    )
    op.create_index("idx_photo_folders_parent", "photo_folders", ["parent_id"])
    op.create_index("idx_photo_folders_path", "photo_folders", ["path"])

    op.create_table(
        "photo_folder_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("photo_folders.id", ondelete="CASCADE"),
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
            "subject_type IN ('user', 'group')", name="ck_photo_folder_perm_subject_type"
        ),
        sa.CheckConstraint(
            "permission IN ('viewer', 'uploader', 'manager')",
            name="ck_photo_folder_perm_permission",
        ),
        sa.UniqueConstraint("folder_id", "subject_id", name="uq_photo_folder_perm_folder_subject"),
    )
    op.create_index("idx_photo_folder_perm_folder", "photo_folder_permissions", ["folder_id"])
    op.create_index("idx_photo_folder_perm_subject", "photo_folder_permissions", ["subject_id"])

    op.create_table(
        "photos",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("photo_folders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exif", postgresql.JSONB(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "inherit_permissions", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "uploaded_by",
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_photos_folder_created", "photos", ["folder_id", sa.text("created_at DESC")]
    )
    op.create_index("idx_photos_taken_at", "photos", [sa.text("taken_at DESC NULLS LAST")])

    op.create_foreign_key(
        "fk_photo_folders_cover",
        "photo_folders",
        "photos",
        ["cover_photo_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_photo_folders_cover", "photo_folders", type_="foreignkey")
    op.drop_table("photos")
    op.drop_table("photo_folder_permissions")
    op.drop_table("photo_folders")
