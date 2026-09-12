"""add erp_absences + erp_absences_runs + absence-filter columns

Revision ID: 092
Revises: 091
Create Date: 2026-08-04

Второй поток ERP-синхронизации — «Отсутствия в офисе» (отпуска/отгулы/болезни/
командировки). ERP (1С) присылает отдельное письмо с отчётом «Кадровая история
сотрудников за период»; портал опрашивает тот же общий IMAP-ящик (ADR-048), но
со своим набором фильтров писем и своей ARQ-задачей.

Отличия от потока «дни рождения» (данные которого — две скалярные колонки на
``users``):

* отсутствия — это **ranged-события** (диапазон дат), нужны отдельная таблица
  ``erp_absences`` (user_id + kind + start_date + end_date);
* контракт — **full-replace**: каждый отчёт самодостаточен («Стандартный период
  01.01.2026 - 31.12.2026», весь год). Перед вставкой удаляем все строки
  ``source='erp_sync'``, затем вставляем заново из файла. Старые записи
  сотрудников, исчезнувших из ERP, стираются автоматически;
* только сопоставленные пользователи (``user_id NOT NULL``) — незнакомые ФИО
  попадают в ``report.unmatched``, в БД не пишутся.

Настройки — **общие** с днями рождения (расширяем singleton ``erp_sync_settings``):
``enabled``/``poll_interval_seconds``/``notify_emails`` общие, per-потоковые —
``absences_poll_enabled`` + 3 фильтра писем + ``absences_expected_interval_days``.

Отдельная таблица логов ``erp_absences_runs`` (клон ``erp_sync_runs``) —
независимый дедуп по ``message_id`` и своя история запусков (контракт дней
рождения не трогаем).

Все изменения additive (zero-downtime): CREATE TABLE, ADD COLUMN с DEFAULT.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "092"
down_revision: str | None = "091"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Основная таблица отсутствий.
    # nosec B608 — статический DDL без интерполяции.
    op.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS erp_absences (
                id           BIGSERIAL PRIMARY KEY,
                user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind         VARCHAR(40) NOT NULL,
                position     TEXT,
                department   TEXT,
                start_date   DATE NOT NULL,
                end_date     DATE NOT NULL,
                source       VARCHAR(20) NOT NULL DEFAULT 'erp_sync',
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_erp_absences_kind CHECK (kind IN (
                    'vacation_main', 'vacation_extra', 'unpaid_leave',
                    'sick', 'business_trip', 'day_off_paid', 'day_off_unpaid'
                )),
                CONSTRAINT ck_erp_absences_dates CHECK (end_date >= start_date),
                CONSTRAINT ck_erp_absences_source CHECK (source IN ('erp_sync', 'manual'))
            )
            """
        )
    )
    # user_id — для «какие отсутствия у сотрудника» (следующая задача, виджет).
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_erp_absences_user_id ON erp_absences (user_id)"))
    # (start_date, end_date) — для «кто отсутствует в диапазоне дат» (range-запросы
    # виджета «кого нет на этой неделе»). btree покрывает как фильтр по
    # пересечению диапазонов, так и ORDER BY start_date.
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_erp_absences_dates "
            "ON erp_absences (start_date, end_date)"
        )
    )

    # 2. Лог импортов отсутствий (клон erp_sync_runs). Независимый message_id-
    # дедуп и своя история — не смешивается с запусками дней рождения.
    op.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS erp_absences_runs (
                id              BIGSERIAL PRIMARY KEY,
                message_id      TEXT UNIQUE,
                attachment_hash TEXT,
                attachment_name TEXT,
                triggered_by    VARCHAR(20) NOT NULL,
                started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                finished_at     TIMESTAMPTZ,
                status          VARCHAR(20) NOT NULL,
                rows_total      INT,
                rows_matched    INT,
                rows_inserted   INT,
                rows_unmatched  INT,
                rows_ambiguous  INT,
                errors          INT,
                report          JSONB NOT NULL DEFAULT '{}'::jsonb,
                CONSTRAINT ck_erp_absences_runs_triggered_by
                    CHECK (triggered_by IN ('cron', 'manual')),
                CONSTRAINT ck_erp_absences_runs_status
                    CHECK (status IN ('success', 'partial', 'failed', 'skipped'))
            )
            """
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_erp_absences_runs_started_at "
            "ON erp_absences_runs (started_at DESC)"
        )
    )

    # 3. Per-потоковые настройки отсутствий (расширяем singleton erp_sync_settings).
    # absences_poll_enabled — отдельный гейтинг авто-поллинга отсутствий (общий
    # poll_enabled относится к дням рождения). Без отдельного флага пустые
    # absences-фильтры (None) пропустили бы ВСЕ письма ящика в absence-парсер.
    op.execute(
        text(
            "ALTER TABLE erp_sync_settings "
            "ADD COLUMN IF NOT EXISTS absences_poll_enabled BOOL "
            "NOT NULL DEFAULT FALSE"
        )
    )
    op.execute(
        text(
            "ALTER TABLE erp_sync_settings "
            "ADD COLUMN IF NOT EXISTS mail_absences_subject_filter VARCHAR(255)"
        )
    )
    op.execute(
        text(
            "ALTER TABLE erp_sync_settings "
            "ADD COLUMN IF NOT EXISTS mail_absences_sender_filter VARCHAR(255)"
        )
    )
    op.execute(
        text(
            "ALTER TABLE erp_sync_settings "
            "ADD COLUMN IF NOT EXISTS mail_absences_attachment_filter VARCHAR(255)"
        )
    )
    # ERP шлёт отчёт отсутствий реж, чем справочник сотрудников (период —
    # месяц/квартал). Watchdog по умолчанию ждёт 7 дней между отчётами.
    op.execute(
        text(
            "ALTER TABLE erp_sync_settings "
            "ADD COLUMN IF NOT EXISTS absences_expected_interval_days INT "
            "NOT NULL DEFAULT 7"
        )
    )


def downgrade() -> None:
    op.execute(
        text("ALTER TABLE erp_sync_settings DROP COLUMN IF EXISTS absences_expected_interval_days")
    )
    op.execute(
        text("ALTER TABLE erp_sync_settings DROP COLUMN IF EXISTS mail_absences_attachment_filter")
    )
    op.execute(
        text("ALTER TABLE erp_sync_settings DROP COLUMN IF EXISTS mail_absences_sender_filter")
    )
    op.execute(
        text("ALTER TABLE erp_sync_settings DROP COLUMN IF EXISTS mail_absences_subject_filter")
    )
    op.execute(text("ALTER TABLE erp_sync_settings DROP COLUMN IF EXISTS absences_poll_enabled"))
    op.execute(text("DROP INDEX IF EXISTS ix_erp_absences_runs_started_at"))
    op.execute(text("DROP TABLE IF EXISTS erp_absences_runs"))
    op.execute(text("DROP INDEX IF EXISTS ix_erp_absences_dates"))
    op.execute(text("DROP INDEX IF EXISTS ix_erp_absences_user_id"))
    op.execute(text("DROP TABLE IF EXISTS erp_absences"))
