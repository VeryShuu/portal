"""KB ACL: section/article permissions, inherit_permissions flag

Revision ID: 009
Revises: 008
Create Date: 2026-04-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_articles",
        sa.Column("inherit_permissions", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "kb_section_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kb_sections.id", ondelete="CASCADE"),
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
        sa.CheckConstraint("subject_type IN ('user', 'group')", name="ck_kb_sec_perm_subject_type"),
        sa.CheckConstraint(
            "permission IN ('viewer', 'editor', 'manager')", name="ck_kb_sec_perm_permission"
        ),
        sa.UniqueConstraint("section_id", "subject_id", name="uq_kb_sec_perm_section_subject"),
    )
    op.create_index("idx_kb_sec_perm_section", "kb_section_permissions", ["section_id"])
    op.create_index("idx_kb_sec_perm_subject", "kb_section_permissions", ["subject_id"])

    op.create_table(
        "kb_article_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kb_articles.id", ondelete="CASCADE"),
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
        sa.CheckConstraint("subject_type IN ('user', 'group')", name="ck_kb_art_perm_subject_type"),
        sa.CheckConstraint(
            "permission IN ('viewer', 'editor', 'manager')", name="ck_kb_art_perm_permission"
        ),
        sa.UniqueConstraint("article_id", "subject_id", name="uq_kb_art_perm_article_subject"),
    )
    op.create_index("idx_kb_art_perm_article", "kb_article_permissions", ["article_id"])
    op.create_index("idx_kb_art_perm_subject", "kb_article_permissions", ["subject_id"])


def downgrade() -> None:
    op.drop_table("kb_article_permissions")
    op.drop_table("kb_section_permissions")
    op.drop_column("kb_articles", "inherit_permissions")
