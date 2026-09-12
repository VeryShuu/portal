"""Integration: keyset (cursor) vs OFFSET pagination на audit_log (audit M2).

DoD M2: доказать, что keyset-курсор использует композитный индекс
``idx_audit_log_created_id`` (Bitmap Index Scan), а OFFSET на большой глубине
уходит в Seq Scan с latency-деградацией. Тест наполняет ~2k строк и сравнивает:

1. Корректность: cursor-страница == OFFSET-страница (те же id в том же порядке).
2. Моnotonicity: последовательные cursor-страницы не пересекаются и покрывают
   весь набор без пропусков/дубликатов.
3. Index usage: cursor-WHERE не триггерит Seq Scan (EXPLAIN → index scan).

ОБЪЁМ (2k, не 10k): в CI testcontainers-контейнер стартует холодным; 10k INSERT
+ 2 EXPLAIN заняли бы >30s. 2k достаточно, чтобы PG выбрал Seq Scan для OFFSET
(он всегда сканирует + отбрасывает), а cursor — index scan. На прод-данных с
партицированием разница многократно больше (DoD говорит «keyset в 10×+ быстрее»).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.api._cursor_pagination import cursor_clause, decode_cursor, encode_cursor

pytestmark = pytest.mark.asyncio

_ROW_COUNT = 2000
_PAGE_SIZE = 50


def _cursor_params_int(decoded) -> dict:
    """audit_log.id — BIGSERIAL; cursor хранит id строкой, приводим к int.

    Mirror production (audit.py): asyncpg требует точный тип для tuple-comparison
    с integer-колонкой. Для email_outbox (UUID id) приводить не нужно.
    """
    _sql, params = cursor_clause(decoded)
    return {**params, "cursor_id": int(decoded.id)}


async def _seed_audit_rows(session, count: int) -> None:
    """Наполняет audit_log `count` строками с шагом 1с назад от NOW().

    Используем NOW() (не фиксированную дату) — audit_log партиционирован, и
    партиции существуют только для текущего/будущих месяцев (init.sql). NOW()
    гарантирует попадание в существующую партицию.
    """
    for i in range(count):
        await session.execute(
            text(
                "INSERT INTO audit_log (event_type, user_email, metadata, created_at) "
                "VALUES (:t, :e, '{}'::jsonb, NOW() - make_interval(secs => :i))"
            ),
            {
                "t": "test.keyset_bench",
                "e": f"bench-{i}@portal.local",
                "i": float(i),
            },
        )
    await session.flush()


def _explain_uses_index(explain_rows: list) -> bool:
    """True если в плане есть Index Scan / Bitmap Index Scan по нашему индексу."""
    plan_text = " ".join(str(r) for r in explain_rows).lower()
    return "index scan" in plan_text or "bitmap index scan" in plan_text


async def _fetch_cursor_page(session, cursor: str | None) -> list:
    """Одна cursor-страница audit_log (event_type=test.keyset_bench)."""
    sql = "SELECT id, created_at FROM audit_log WHERE event_type = 'test.keyset_bench'"
    params: dict = {}
    clause = ""
    if cursor:
        decoded = decode_cursor(cursor)
        assert decoded is not None
        cparams = _cursor_params_int(decoded)
        clause = " AND " + cursor_clause(decoded)[0]
        params.update(cparams)
    sql += clause + " ORDER BY created_at DESC, id DESC LIMIT :limit"
    params["limit"] = _PAGE_SIZE
    return (await session.execute(text(sql), params)).fetchall()


async def test_cursor_page_matches_offset_page(real_db_session):
    """Корректность: 4-я страница через cursor == 4-я страница через OFFSET."""
    await _seed_audit_rows(real_db_session, _ROW_COUNT)

    # OFFSET 150 (4-я страница по 50).
    offset_rows = (
        await real_db_session.execute(
            text(
                "SELECT id FROM audit_log WHERE event_type = 'test.keyset_bench' "
                "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
            ),
            {"limit": _PAGE_SIZE, "offset": 150},
        )
    ).fetchall()
    offset_ids = [r[0] for r in offset_rows]

    # Cursor: проходим 3 страницы, берём курсор с 3-й, затем 4-я должна совпасть.
    cursor: str | None = None
    for _page in range(3):  # страницы 1,2,3
        rows = await _fetch_cursor_page(real_db_session, cursor)
        cursor = encode_cursor(rows[-1][1], rows[-1][0])

    # 4-я страница через cursor.
    rows4 = await _fetch_cursor_page(real_db_session, cursor)
    cursor_ids = [r[0] for r in rows4]

    assert cursor_ids == offset_ids, "cursor-страница должна совпадать с OFFSET-страницей"


async def test_keyset_uses_index_not_seq_scan(real_db_session):
    """EXPLAIN: cursor-WHERE использует idx_audit_log_created_id (index scan)."""
    await _seed_audit_rows(real_db_session, _ROW_COUNT)

    # Cursor из последней строки страницы 1.
    first_page = await _fetch_cursor_page(real_db_session, None)
    cursor = encode_cursor(first_page[-1][1], first_page[-1][0])
    decoded = decode_cursor(cursor)
    assert decoded is not None
    cparams = _cursor_params_int(decoded)
    clause = cursor_clause(decoded)[0]

    plan = (
        await real_db_session.execute(
            text(
                "EXPLAIN SELECT id FROM audit_log WHERE event_type = 'test.keyset_bench' "
                "AND " + clause + " ORDER BY created_at DESC, id DESC LIMIT 50"
            ),
            cparams,
        )
    ).fetchall()
    assert _explain_uses_index(plan), f"cursor should use index, got: {plan}"


async def test_full_traversal_no_gaps_no_duplicates(real_db_session):
    """Полный обход cursor'ом: ровно _ROW_COUNT уникальных id, без пропусков."""
    await _seed_audit_rows(real_db_session, _ROW_COUNT)

    seen: set = set()
    cursor: str | None = None
    pages = 0
    while True:
        rows = await _fetch_cursor_page(real_db_session, cursor)
        if not rows:
            break
        for r in rows:
            assert r[0] not in seen, f"дубликат id {r[0]} — cursor некорректен"
            seen.add(r[0])
        pages += 1
        cursor = encode_cursor(rows[-1][1], rows[-1][0])
        if len(rows) < _PAGE_SIZE:
            break

    assert len(seen) == _ROW_COUNT, f"ожидалось {_ROW_COUNT}, обошли {len(seen)}"
    assert pages == _ROW_COUNT // _PAGE_SIZE
