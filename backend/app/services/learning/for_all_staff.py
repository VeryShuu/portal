"""Массовое покрытие обязательных курсов «для всех сотрудников».

Set-based дозачисление после Keycloak-синка (worker/tasks/news.py): новые
сотрудники покрываются первым же прогоном после появления в Keycloak.
Работает на raw-соединении (asyncpg) — как сам sync: роль learning_app
сюда не участвует, SQL идёт от владельца БД. Идемпотентно (NOT EXISTS);
письма не рассылаются (массовое покрытие, миграция 111).
"""

from __future__ import annotations

import asyncpg

ENROLL_MISSING_SQL = """
    WITH inserted AS (
        INSERT INTO learning_course_participants
            (course_id, user_id, display_name, email)
        SELECT c.id, u.id, u.full_name, u.email
        FROM learning_courses c
        JOIN users u ON u.deleted_at IS NULL
        WHERE c.deleted_at IS NULL
          AND c.status = 'published'
          AND c.for_all_staff
          AND NOT EXISTS (
              SELECT 1 FROM learning_course_participants p
              WHERE p.course_id = c.id
                AND p.user_id = u.id
                AND p.deleted_at IS NULL
          )
        RETURNING course_id
    )
    SELECT count(*) FROM inserted
"""


async def enroll_missing_staff(conn: asyncpg.Connection) -> int:
    """Дозачислить всех сотрудников без явной строки во все обязательные
    опубликованные курсы. Возвращает число созданных строк."""
    enrolled = await conn.fetchval(ENROLL_MISSING_SQL)
    return int(enrolled)
