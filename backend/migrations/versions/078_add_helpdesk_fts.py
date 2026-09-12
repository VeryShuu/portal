"""add helpdesk full-text search (tsvector + GIN on tickets + messages)

Revision ID: 078
Revises: 077
Create Date: 2026-07-16

Полнотекстовый поиск по тикетам helpdesk (замена ilike в агентском инбоксе):
* ``helpdesk_tickets.search_tsvector`` — over (subject + description);
* ``helpdesk_messages.body_tsvector`` — over (body_text, тела ответов).

Использует единую для портала конфигурацию ``russian_hunspell`` (создаётся в
``init.sql`` поверх hunspell-словарей; тот же regconfig, что в KB-статьях и
новостях — миграции 008, 011). Поиск идёт по subject+description тикета ИЛИ по
телам ответов (EXISTS по messages), плюс ``requester_email`` через ``ilike``.

Generated STORED-колонки вычисляются атомарно при ``ADD COLUMN`` (zero-downtime:
существующие строки заполняются сразу). GIN-индексы строятся на существующих
данных — на ~сотнях тикетов/тысячах сообщений это мгновенно.

DDL через ``op.execute`` (консистентно с миграциями 075/077 — hand-written).
``IF NOT EXISTS`` для идемпотентности (повторный apply — no-op).
"""

from alembic import op

revision: str = "078"
down_revision: str | None = "077"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # helpdesk_tickets: tsvector over (subject + description).
    op.execute(
        "ALTER TABLE helpdesk_tickets "
        "ADD COLUMN IF NOT EXISTS search_tsvector TSVECTOR "
        "GENERATED ALWAYS AS ("
        "  to_tsvector('russian_hunspell',"
        "    coalesce(subject, '') || ' ' || coalesce(description, ''))"
        ") STORED"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_helpdesk_tickets_fts "
        "ON helpdesk_tickets USING gin (search_tsvector)"
    )

    # helpdesk_messages: tsvector over (body_text, тела ответов/заметок).
    # Только plain body_text — HTML-теги засоряли бы вектор.
    op.execute(
        "ALTER TABLE helpdesk_messages "
        "ADD COLUMN IF NOT EXISTS body_tsvector TSVECTOR "
        "GENERATED ALWAYS AS ("
        "  to_tsvector('russian_hunspell', coalesce(body_text, ''))"
        ") STORED"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_helpdesk_messages_fts "
        "ON helpdesk_messages USING gin (body_tsvector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_helpdesk_messages_fts")
    op.execute("ALTER TABLE helpdesk_messages DROP COLUMN IF EXISTS body_tsvector")
    op.execute("DROP INDEX IF EXISTS idx_helpdesk_tickets_fts")
    op.execute("ALTER TABLE helpdesk_tickets DROP COLUMN IF EXISTS search_tsvector")
