"""file_items: dedup active rows + partial unique index on (folder_id, name)

Перезалив файла с существующим именем раньше создавал второй активный
``FileItem`` (F2). Это ломало ``delete_file`` (scalar_one_or_none →
MultipleResultsFound → HTTP 500) и засоряло БД дублями.

1) Бэкфилл: для каждой группы (folder_id, name) среди активных
   (``deleted_at IS NULL``) записей оставляем самую свежую
   (``uploaded_at DESC, id DESC``), остальные мягко удаляем.
2) Частичный UNIQUE-индекс не даёт появиться новым активным дублям.

Revision ID: 066
Revises: 065
Create Date: 2026-06-06
"""

from alembic import op

revision: str = "066"
down_revision: str | None = "065"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY folder_id, name
                       ORDER BY uploaded_at DESC, id DESC
                   ) AS rn
            FROM file_items
            WHERE deleted_at IS NULL
        )
        UPDATE file_items
        SET deleted_at = NOW()
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
    )
    op.create_index(
        "uq_file_items_folder_name_active",
        "file_items",
        ["folder_id", "name"],
        unique=True,
        postgresql_where="deleted_at IS NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_file_items_folder_name_active", table_name="file_items")
