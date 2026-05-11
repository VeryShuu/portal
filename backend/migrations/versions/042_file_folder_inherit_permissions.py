"""file_folders: add inherit_permissions column

Revision ID: 042
Revises: 041
Create Date: 2026-05-11

When inherit_permissions is TRUE (default) the folder inherits ACL from its
parent — the existing recursive CTE walks up the ancestor chain.
When FALSE the resolution stops at this folder: only direct permissions on
the folder itself are considered, regardless of what is set on any parent.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "042"
down_revision: Union[str, None] = "041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "file_folders",
        sa.Column(
            "inherit_permissions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
    )


def downgrade() -> None:
    op.drop_column("file_folders", "inherit_permissions")
