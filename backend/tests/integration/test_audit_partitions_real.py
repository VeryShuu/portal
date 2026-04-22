"""Integration: реальные партиции audit_log в PG.

Init.sql создаёт первые 3 партиции; проверяем insert-routing.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.asyncio


async def test_audit_log_table_is_partitioned(real_db_session):
    """audit_log — partitioned table с PARTITION BY RANGE(created_at)."""
    rows = (
        await real_db_session.execute(
            text("""
                SELECT partstrat
                FROM pg_partitioned_table p
                JOIN pg_class c ON c.oid = p.partrelid
                WHERE c.relname = 'audit_log'
            """)
        )
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "r"  # range


async def test_initial_partitions_created(real_db_session):
    """init.sql создаёт минимум 3 партиции (текущий + 2 месяца)."""
    rows = (
        await real_db_session.execute(
            text("""
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname LIKE 'audit_log_%'
                  AND c.relkind = 'r'
            """)
        )
    ).fetchall()
    partitions = {r[0] for r in rows}
    assert len(partitions) >= 3, f"Ожидалось >= 3 партиции, получили {len(partitions)}: {partitions}"


async def test_audit_insert_routes_to_current_partition(real_db_session):
    """INSERT с created_at=сейчас должен попасть в партицию текущего месяца."""
    user_email = f"audit-{uuid.uuid4().hex[:6]}@portal.local"
    await real_db_session.execute(
        text("""
            INSERT INTO audit_log (event_type, user_email, metadata, created_at)
            VALUES (:t, :e, '{}'::jsonb, NOW())
        """),
        {"t": "test.partition_route", "e": user_email},
    )
    await real_db_session.commit()

    rows = (
        await real_db_session.execute(
            text("""
                SELECT tableoid::regclass::text AS partition
                FROM audit_log
                WHERE user_email = :e
            """),
            {"e": user_email},
        )
    ).fetchall()
    assert len(rows) == 1
    now = datetime.now(UTC)
    expected_part = f"audit_log_{now.year}_{now.month:02d}"
    assert rows[0][0].endswith(expected_part)
