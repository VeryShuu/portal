"""add index notifications(created_at) for cleanup scan

Revision ID: 085
Revises: 084
Create Date: 2026-07-30

Автоочистка старых уведомлений (cron ``notifications.cleanup_notifications``)
делает глобальный ``DELETE FROM notifications WHERE created_at < :cutoff``,
а не per-user скан. Существующие индексы ``ix_notifications_user_*`` ведут
``user_id`` и такой запрос не используют — планировщик уходит в seq scan, что
на растущей таблице unnecessarily дорого каждый день.

``ix_notifications_created_at`` — компактный btree на ``created_at``, покрывает
cleanup-скан за O(log n + k). DDL через ``op.execute`` (консистентно с 012/075–084,
hand-written), ``CREATE INDEX IF NOT EXISTS`` для идемпотентности.

На проде ~300 пользователей × ~90 дней ≈ 270K строк — однопроходный DELETE из
``cleanup_old_notifications`` достаточен; индекс держит ежедневный скан дешёвым.
"""

from alembic import op

revision: str = "085"
down_revision: str | None = "084"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notifications_created_at")
