"""fk set null notifications bookmarks user_id

Revision ID: 032
Revises: 031
Create Date: 2026-05-04

Change notifications.user_id and bookmarks.user_id from ON DELETE CASCADE
to ON DELETE SET NULL so that deleting a (soft-)deleted user does not erase
the notification/bookmark history required for audit and analytics.

Zero-downtime steps:
  1. Make user_id nullable (new rows tolerate NULL)
  2. Drop old CASCADE FK
  3. Add new SET NULL FK
No index changes needed — existing indexes handle NULL user_id gracefully.
"""


import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "032"
down_revision: str | None = "031"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.alter_column("user_id", existing_type=UUID(as_uuid=True), nullable=True)
        batch_op.drop_constraint("notifications_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "notifications_user_id_fkey",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("bookmarks") as batch_op:
        batch_op.alter_column("user_id", existing_type=UUID(as_uuid=True), nullable=True)
        batch_op.drop_constraint("bookmarks_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "bookmarks_user_id_fkey",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("bookmarks") as batch_op:
        batch_op.drop_constraint("bookmarks_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "bookmarks_user_id_fkey",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.alter_column("user_id", existing_type=UUID(as_uuid=True), nullable=False)

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_constraint("notifications_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "notifications_user_id_fkey",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.alter_column("user_id", existing_type=UUID(as_uuid=True), nullable=False)
