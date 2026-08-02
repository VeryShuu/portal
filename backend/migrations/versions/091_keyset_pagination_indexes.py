"""add composite indexes for keyset pagination (audit_log, email_outbox)

Revision ID: 091
Revises: 090
Create Date: 2026-08-02

audit M2: OFFSET-пагинация на растущих таблицах (audit_log, email_outbox)
деградирует линейно — OFFSET 10000 + ORDER BY created_at заставляет БД сканировать
и отбрасывать 10k строк. Keyset-курсор ``WHERE (created_at, id) < (:last_ca, :last_id)``
работает за O(log n), но требует композитного btree-индекса на ``(created_at DESC, id DESC)``.

Существующие индексы:
- audit_log: PK (id, created_at), idx_audit_user_time, idx_audit_event_time — ни один
  не покрывает «все строки, сортировка по created_at DESC» без фильтра.
- email_outbox: idx_email_outbox_status_created(status, created_at DESC) — не покрывает
  случай без status-фильтра + не включает id для стабильности курсора.

Новые индексы:
- ``idx_audit_log_created_id`` на audit_log (created_at DESC, id DESC).
- ``idx_email_outbox_created_id`` на email_outbox (created_at DESC, id DESC).

NOTE: CREATE INDEX CONCURRENTLY не поддерживается на партиционированных таблицах
(см. миграцию 033 — PostgreSQL limitation), поэтому audit_log — обычный CREATE INDEX
(PG автоматически развернёт partitioned index на все партиции). email_outbox не
партиционирован — но для консистентности с проектным zero-downtime-паттерном тоже
используем обычный CREATE INDEX (админ-endpoint, нагрузка низкая; CONCURRENTLY здесь
можно, но единообразие важнее). IF NOT EXISTS для идемпотентности.
"""

from alembic import op

revision: str = "091"
down_revision: str | None = "090"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_log_created_id "
        "ON audit_log (created_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_outbox_created_id "
        "ON email_outbox (created_at DESC, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_email_outbox_created_id")
    op.execute("DROP INDEX IF EXISTS idx_audit_log_created_id")
