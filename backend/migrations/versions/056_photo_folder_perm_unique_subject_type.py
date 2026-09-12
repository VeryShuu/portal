"""photo_folder_permissions: add subject_type to unique constraint

Revision ID: 056
Revises: 055
Create Date: 2026-05-22
"""

import sqlalchemy as sa
from alembic import op

revision: str = "056"
down_revision: str | None = "055"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_photo_folder_perm_folder_subject",
        "photo_folder_permissions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_photo_folder_perm_folder_subject",
        "photo_folder_permissions",
        ["folder_id", "subject_type", "subject_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_photo_folder_perm_folder_subject",
        "photo_folder_permissions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_photo_folder_perm_folder_subject",
        "photo_folder_permissions",
        ["folder_id", "subject_id"],
    )
