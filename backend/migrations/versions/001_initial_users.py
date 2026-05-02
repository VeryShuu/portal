"""initial users table

Revision ID: 001
Revises:
Create Date: 2026-04-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("keycloak_id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("position", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="reader"),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("presence_status", sa.String(20), nullable=False, server_default="office"),
        sa.Column("notify_email", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_inapp", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("lang", sa.String(5), nullable=False, server_default="ru"),
        sa.Column("preferences", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('reader', 'editor', 'admin')", name="ck_users_role"),
        sa.CheckConstraint(
            "presence_status IN ('office', 'remote', 'vacation')",
            name="ck_users_presence_status",
        ),
        sa.CheckConstraint("lang IN ('ru', 'en')", name="ck_users_lang"),
        sa.UniqueConstraint("keycloak_id", name="uq_users_keycloak_id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_index("idx_users_keycloak", "users", ["keycloak_id"])
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_dept", "users", ["department"])

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("response", JSONB(), nullable=False, server_default="{}"),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("idx_idempotency_created", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("users")
