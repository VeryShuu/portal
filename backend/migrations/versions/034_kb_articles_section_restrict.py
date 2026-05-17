"""kb_articles.section_id: ON DELETE SET NULL → RESTRICT

Section deletion is now blocked at the DB level if any article (active or
soft-deleted) still references the section.  The application endpoint handles
this explicitly:
  - active articles (deleted_at IS NULL)  → 409 before the DELETE
  - soft-deleted articles                 → section_id is set to NULL
    before the DELETE so the RESTRICT constraint is not triggered

Revision ID: 034
Revises: 033
Create Date: 2026-05-04
"""


from alembic import op

revision: str = "034"
down_revision: str | None = "033"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "kb_articles_section_id_fkey",
        "kb_articles",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "kb_articles_section_id_fkey",
        "kb_articles",
        "kb_sections",
        ["section_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "kb_articles_section_id_fkey",
        "kb_articles",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "kb_articles_section_id_fkey",
        "kb_articles",
        "kb_sections",
        ["section_id"],
        ["id"],
        ondelete="SET NULL",
    )
