"""photo_folders parent_id: ON DELETE CASCADE → RESTRICT

CASCADE is dangerous with soft-delete: a direct physical DELETE on a parent
row (e.g. via psql) would silently wipe the entire subtree. RESTRICT prevents
physical deletion of any folder that still has children, forcing the operator
to clean up children first — consistent with the soft-delete-everywhere policy.

Revision ID: 031
Revises: 030
Create Date: 2026-05-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "photo_folders_parent_id_fkey",
        "photo_folders",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "photo_folders_parent_id_fkey",
        "photo_folders",
        "photo_folders",
        ["parent_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "photo_folders_parent_id_fkey",
        "photo_folders",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "photo_folders_parent_id_fkey",
        "photo_folders",
        "photo_folders",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )
