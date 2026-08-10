"""extend helpdesk search_tsvector with requester_name (ФИО инициатора)

Revision ID: 094
Revises: 093
Create Date: 2026-08-10

Расширяет полнотекстовый поиск тикетов helpdesk именем/фамилией заявителя.
До миграции ``search_tsvector`` покрывал только ``subject + description`` (миграция
078) — поиск по ФИО инициатора в агентском инбоксе ничего не находил, хотя имя
заявителя видно в списке.

Теперь выражение generated-колонки: ``subject || description || requester_name``.
Поиск по-прежнему идёт через ``search_tsvector @@ websearch_to_tsquery(...)``
(код запроса в ``_agent_filter_conditions`` не меняется) — индекс автоматически
начинает матчить имена. Морфология hunspell на ФИО ограничена (нет stemming для
фамилий), но точное совпадение и словоформы ищет.

Архитектурное ограничение: generated STORED column не может JOIN'ить к
``users.full_name`` — только колонки своей же строки. ``requester_name`` —
snapshot-колонка на ``helpdesk_tickets`` (для web = ``user.full_name``, для email
= display-name из ``From``), поэтому включить её в выражение можно. Это
согласуется с конвенцией проекта (KB/news: ``title || body`` в одном tsvector) и
со snapshot-at-write + live-fallback-at-read (display-слой
``_requester_display_name`` уже предпочитает снимок — индексируем ровно то, что
видим в списке).

Email остаётся на ``ilike`` (адреса плохо матчатся tsquery — ``@``/точки/
домены не нормализуются); это осознанное решение миграции 078.

PostgreSQL не умеет менять выражение generated column через ``ALTER COLUMN`` —
только drop + re-add. Поэтому миграция пересоздаёт колонку и GIN-индекс. На
~сотнях тикетов пересчёт мгновенный (zero-downtime не нарушается).
``helpdesk_messages.body_tsvector`` не затрагивается.

DDL через ``op.execute`` (консистентно с миграциями 075/077/078 — hand-written).
``IF EXISTS``/``IF NOT EXISTS`` для идемпотентности (повторный apply — no-op).
"""

from alembic import op

revision: str = "094"
down_revision: str | None = "093"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # PostgreSQL не позволяет ALTER выражение generated column — только drop + re-add.
    # GIN-индекс нужно снять до drop колонки, иначе DROP COLUMN CASCADE приберёт и его
    # (но явный DROP INDEX чище и не зависит от каскада).
    op.execute("DROP INDEX IF EXISTS idx_helpdesk_tickets_fts")
    op.execute("ALTER TABLE helpdesk_tickets DROP COLUMN IF EXISTS search_tsvector")

    # Расширенное выражение: subject + description + requester_name.
    op.execute(
        "ALTER TABLE helpdesk_tickets "
        "ADD COLUMN IF NOT EXISTS search_tsvector TSVECTOR "
        "GENERATED ALWAYS AS ("
        "  to_tsvector('russian_hunspell',"
        "    coalesce(subject, '') || ' ' || coalesce(description, '')"
        "    || ' ' || coalesce(requester_name, ''))"
        ") STORED"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_helpdesk_tickets_fts "
        "ON helpdesk_tickets USING gin (search_tsvector)"
    )


def downgrade() -> None:
    # Откат к выражению миграции 078 (subject + description, без requester_name).
    op.execute("DROP INDEX IF EXISTS idx_helpdesk_tickets_fts")
    op.execute("ALTER TABLE helpdesk_tickets DROP COLUMN IF EXISTS search_tsvector")
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
