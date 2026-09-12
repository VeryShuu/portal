"""drop helpdesk `resolved` status — unified `closed` as the only final state

Revision ID: 079
Revises: 078
Create Date: 2026-07-17

Решение владельца: убрать двухфазное закрытие (resolved → ждём подтверждения →
closed). Теперь только ``closed`` = единый финал (агент завершил работу → тикет
уходит в архив по ``HELPDESK_ARCHIVE_AFTER_DAYS``). Reopen из ``closed`` — окно
``HELPDESK_REOPEN_WINDOW_DAYS`` (7 дней, без изменений).

Data-migration обязателен: ``archive_closed_tickets`` архивирует только ``closed``
(``archive.py`` игнорирует не-closed). Оставленные ``resolved``-тикеты зависли бы
вечно (cron ``auto_close_resolved_tickets`` удалён в этом же коммите, пути в
``closed`` для них больше нет). Поэтому переводим существующие resolved → closed,
``closed_at = last_activity_at`` (чтобы честно ушли в архив по сроку, а не
«прожили» лишние дни).

CHECK-констрейнт ``ck_helpdesk_status`` (миграция 075): убираем ``'resolved'``
из допустимых значений. Идемпотентно (UPDATE 0 строк — норма).

DDL через ``op.execute`` (консистентно с миграциями 075/077/078 — hand-written).
"""

from alembic import op

revision: str = "079"
down_revision: str | None = "078"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Data-migration: существующие resolved → closed. closed_at берём из
    #    last_activity_at (если ещё не заполнен) — осмысленная дата закрытия.
    op.execute(
        "UPDATE helpdesk_tickets "
        "SET status = 'closed', "
        "    closed_at = COALESCE(closed_at, last_activity_at) "
        "WHERE status = 'resolved'"
    )
    # 2. CHECK-констрейнт: убрать 'resolved'. DROP + ADD (IF EXISTS на DROP для
    #    идемпотентности при повторном apply).
    op.execute("ALTER TABLE helpdesk_tickets DROP CONSTRAINT IF EXISTS ck_helpdesk_status")
    op.execute(
        "ALTER TABLE helpdesk_tickets ADD CONSTRAINT ck_helpdesk_status "
        "CHECK (status IN ('new','open','pending','closed'))"
    )


def downgrade() -> None:
    # Возврат 'resolved' в CHECK (данные не восстанавливаем — reverse data-mig
    # неоднозначен: какие closed перевести назад в resolved?).
    op.execute("ALTER TABLE helpdesk_tickets DROP CONSTRAINT IF EXISTS ck_helpdesk_status")
    op.execute(
        "ALTER TABLE helpdesk_tickets ADD CONSTRAINT ck_helpdesk_status "
        "CHECK (status IN ('new','open','pending','resolved','closed'))"
    )
