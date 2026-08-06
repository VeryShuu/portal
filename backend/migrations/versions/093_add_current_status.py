"""add users.current_status/_until (computed from erp_absences), drop presence_status

Revision ID: 093
Revises: 092
Create Date: 2026-08-05

Единый статус присутствия сотрудника, вычисляемый из ERP-импорта отсутствий
(``erp_absences``). Заменяет древний ручной ``users.presence_status``
(``office``/``remote``/``vacation``) — источник истины теперь ERP, ручной выбор
убран.

Две денормализованные колонки на ``users`` (чтобы не было N+1 JOIN в списках —
все ``users_repo`` SELECT'ы тянут ``select(User)`` целиком и подхватят их
бесплатно):

* ``current_status VARCHAR(20) NOT NULL DEFAULT 'working'`` — категория:
  ``working`` / ``vacation`` / ``sick`` / ``business_trip``. CHECK enum.
* ``current_status_until DATE NULL`` — конец текущей активной absence
  (для tooltip «до 15 авг»).

Категория ← ERP-kind (маппинг в ``app/services/erp_sync/absences_status.py``):
``vacation_main``/``vacation_extra``/``unpaid_leave``/``day_off_paid``/
``day_off_unpaid`` → ``vacation``; ``sick`` → ``sick``; ``business_trip`` →
``business_trip``. Приоритет при пересечении: ``sick`` > ``vacation`` >
``business_trip``.

Пересчёт:
* в конце ``absences_importer.run_absences_import`` (затронутые user_id);
* ежедневным cron'ом ``recompute_daily_presence_status`` (полный пересчёт,
  для перехода дат — вчерашний отпуск кончился → ``working``).

Backfill в этой миграции выставляет ``current_status`` по активным на сегодня
отсутствиям (один UPDATE с CTE + DISTINCT ON, опирается на
``ix_erp_absences_dates``). ``presence_status`` дропается в том же деплое —
колонка без FK/индексов, безопасный destructive-шаг.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "093"
down_revision: str | None = "092"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Новые колонки (additive, с DEFAULT → NOT NULL безопасно).
    op.execute(
        text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS current_status VARCHAR(20) "
            "NOT NULL DEFAULT 'working'"
        )
    )
    op.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS current_status_until DATE"))
    op.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_current_status"))
    op.execute(
        text(
            "ALTER TABLE users ADD CONSTRAINT ck_users_current_status "
            "CHECK (current_status IN ('working', 'vacation', 'sick', 'business_trip'))"
        )
    )

    # 2. Backfill: для каждого пользователя с активной на сегодня absence (today ∈
    # [start_date, end_date]) выбрать приоритетную запись и проставить категорию.
    # Приоритет: sick (0) > vacation (1) > business_trip (2). DISTINCT ON (user_id)
    # + ORDER BY user_id, priority ASC оставляет одну строку на пользователя.
    # nosec B608 — статический SQL без интерполяции пользовательских данных.
    op.execute(
        text(
            """
            UPDATE users u
            SET current_status = sub.category,
                current_status_until = sub.end_date
            FROM (
                SELECT DISTINCT ON (ea.user_id)
                       ea.user_id,
                       ea.end_date,
                       CASE ea.kind
                           WHEN 'sick' THEN 'sick'
                           WHEN 'business_trip' THEN 'business_trip'
                           ELSE 'vacation'
                       END AS category,
                       CASE ea.kind
                           WHEN 'sick' THEN 0
                           WHEN 'business_trip' THEN 2
                           ELSE 1
                       END AS priority
                FROM erp_absences ea
                WHERE ea.start_date <= CURRENT_DATE
                  AND ea.end_date >= CURRENT_DATE
                ORDER BY ea.user_id, priority ASC, ea.end_date DESC
            ) sub
            WHERE u.id = sub.user_id
            """
        )
    )

    # 3. Дропаем древний ручной presence_status (источник истины — только ERP).
    op.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_presence_status"))
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS presence_status"))


def downgrade() -> None:
    # Восстанавливаем presence_status (default 'office', как в миграции 001).
    op.execute(
        text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS presence_status VARCHAR(20) "
            "NOT NULL DEFAULT 'office'"
        )
    )
    op.execute(
        text(
            "ALTER TABLE users ADD CONSTRAINT ck_users_presence_status "
            "CHECK (presence_status IN ('office', 'remote', 'vacation'))"
        )
    )
    # Убираем вычисляемые колонки.
    op.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_current_status"))
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS current_status_until"))
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS current_status"))
