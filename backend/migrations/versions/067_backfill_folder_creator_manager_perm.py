"""backfill: materialize folder creator `manager` rows in file_folder_permissions

Раньше право создателя папки выдавалось только виртуально в памяти
(``resolve_folder_permission``: ``if created_by == user.id -> 'manager'``),
без записи в ``file_folder_permissions``. Рекурсивный ACL-CTE ищет права
только в таблице, поэтому создатель не видел подпапки, созданные внутри
другими пользователями (F3).

С этой миграции создатель материализуется реальной строкой при создании
папки; здесь дозаполняем существующие папки (включая soft-deleted —
безвредно). ``ON CONFLICT`` по ``uq_file_folder_perm_folder_subject``
делает миграцию идемпотентной и не трогает уже выданные права.

Revision ID: 067
Revises: 066
Create Date: 2026-06-06
"""

from alembic import op

revision: str = "067"
down_revision: str | None = "066"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO file_folder_permissions
            (id, folder_id, subject_type, subject_id, subject_name,
             permission, granted_by, created_at)
        SELECT gen_random_uuid(), f.id, 'user', u.id::text,
               COALESCE(NULLIF(u.full_name, ''), u.email),
               'manager', u.id, NOW()
        FROM file_folders f
        JOIN users u ON u.id = f.created_by
        WHERE f.created_by IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_file_folder_perm_folder_subject DO NOTHING
        """
    )


def downgrade() -> None:
    # Удаляем только материализованные строки создателей: те, где
    # subject указывает на создателя соответствующей папки.
    op.execute(
        """
        DELETE FROM file_folder_permissions p
        USING file_folders f
        WHERE p.folder_id = f.id
          AND p.subject_type = 'user'
          AND p.permission = 'manager'
          AND p.subject_id = f.created_by::text
        """
    )
