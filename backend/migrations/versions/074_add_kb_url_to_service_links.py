"""add_kb_url_to_service_links

Revision ID: 074
Revises: 073
Create Date: 2026-06-20

"""
from alembic import op
import sqlalchemy as sa

revision: str = '074'
down_revision: str | None = '073'
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column('service_links', sa.Column('kb_url', sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column('service_links', 'kb_url')
