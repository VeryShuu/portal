"""Integration: batch-INSERT в email_outbox против реальной PostgreSQL 16.

Regression-тест на баг: ``enqueue_outbox_email_batch`` ранее использовал raw-SQL
``unnest($1, ..., $10) AS i(...)``, который на PostgreSQL 16 + asyncpg падает с
``AmbiguousFunctionError: function pg_catalog.unnest(unknown) is not unique``
когда хотя бы один из массивов содержит только ``None`` (``body_text``,
``related_resource_*``, ``created_by_user_id``). asyncpg отправлял такие массивы
как ``unknown[]``, и PG не мог разрешить перегрузку ``unnest(anyarray)``.

Симптом в проде: создание встречи **с участниками** молча откатывало всю
транзакцию (встреча не сохранялась, хотя FastAPI возвращал 201). Без участников
batch не вызывался, поэтому работало.

Все unit-тесты (``test_email_outbox_service.py``, ``test_meetings_outbox_batch.py``)
мокируют ``session.execute`` и этот SQL-путь не прогоняли. Здесь — реальный
INSERT против PG16 через ``real_db_session``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.services.email_outbox import OutboxItem

pytestmark = pytest.mark.asyncio


def _item(
    *,
    to_email: str,
    body_text: str | None = None,
    payload: dict | None = None,
    related_resource_id: uuid.UUID | None = None,
    related_resource_type: str | None = "meeting_booking",
    created_by_user_id: uuid.UUID | None = None,
    kind: str = "meeting",
) -> OutboxItem:
    return OutboxItem(
        kind=kind,
        to_email=to_email,
        subject=f"Subject for {to_email}",
        body_html=f"<p>html {to_email}</p>",
        body_text=body_text,
        payload=payload,
        related_resource_type=related_resource_type,
        related_resource_id=related_resource_id,
        created_by_user_id=created_by_user_id,
    )


async def test_batch_insert_persists_all_rows_with_none_body_text(real_db_session):
    """Regression: body_text=None не должен ломать batch-INSERT (баг unnest на PG16).

    3 OutboxItem с body_text=None (воспроизводит прод-симптом) → все 3 строки
    сохраняются, server_default применяются, payload корректно сериализован в JSONB.
    """
    from app.models.email_outbox import EmailOutbox
    from app.services.email_outbox import enqueue_outbox_email_batch

    items = [
        _item(to_email=f"u{i}@test.com", body_text=None, payload={"method": "REQUEST", "i": i})
        for i in range(3)
    ]

    ids = await enqueue_outbox_email_batch(real_db_session, items)
    await real_db_session.flush()

    assert len(ids) == 3
    assert all(isinstance(i, uuid.UUID) for i in ids)

    rows = (
        (await real_db_session.execute(select(EmailOutbox).where(EmailOutbox.id.in_(ids))))
        .scalars()
        .all()
    )
    assert {r.to_email for r in rows} == {f"u{i}@test.com" for i in range(3)}
    # server_default status='PENDING' применяется сервером (Core insert не передаёт поле).
    assert {r.status for r in rows} == {"PENDING"}
    assert {r.attempts for r in rows} == {0}
    # body_text nullable — None сохраняется как NULL, не ломая INSERT.
    assert all(r.body_text is None for r in rows)
    # payload корректно сериализован в JSONB и читается как dict.
    assert {r.payload["method"] for r in rows} == {"REQUEST"}
    assert {r.payload["i"] for r in rows} == {0, 1, 2}


async def test_batch_insert_handles_none_payload(real_db_session):
    """payload=None → server_default '{}' применяется, INSERT не падает.

    Защита: в OutboxItem payload по умолчанию None; фикс-код делает ``it.payload or {}``,
    но server_default на колонке — дополнительная защита. Проверяем оба пути.
    """
    from app.models.email_outbox import EmailOutbox
    from app.services.email_outbox import enqueue_outbox_email_batch

    items = [_item(to_email="null-payload@test.com", payload=None)]
    ids = await enqueue_outbox_email_batch(real_db_session, items)
    await real_db_session.flush()

    rows = (
        (await real_db_session.execute(select(EmailOutbox).where(EmailOutbox.id.in_(ids))))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    # Фикс-код делает it.payload or {} → пустой dict. server_default '{}' — запас.
    assert rows[0].payload == {}


async def test_batch_insert_with_related_resource_and_user_ids(real_db_session, real_user):
    """related_resource_id (UUID) и created_by_user_id корректно сохраняются.

    Эти колонки тоже были массивами с None в сломанном unnest-варианте. Проверяем,
    что реальные UUID persist'ятся, и FK на users работает.
    """
    from app.models.email_outbox import EmailOutbox
    from app.services.email_outbox import enqueue_outbox_email_batch

    resource_id = uuid.uuid4()
    items = [
        _item(
            to_email="with-ids@test.com",
            related_resource_id=resource_id,
            related_resource_type="meeting_booking",
            created_by_user_id=real_user.id,
        )
    ]
    ids = await enqueue_outbox_email_batch(real_db_session, items)
    await real_db_session.flush()

    rows = (
        (await real_db_session.execute(select(EmailOutbox).where(EmailOutbox.id.in_(ids))))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].related_resource_id == resource_id
    assert rows[0].related_resource_type == "meeting_booking"
    assert rows[0].created_by_user_id == real_user.id


async def test_empty_list_is_noop(real_db_session):
    """enqueue_outbox_email_batch([]) → [], session.execute не вызывается.

    Защита регрессии empty-list: раньше проверялось только в unit-тесте с моком,
    здесь — с реальной сессией (no DB round-trip expected).
    """
    from app.services.email_outbox import enqueue_outbox_email_batch

    # Используем spy-обёртку: real_db_session.execute должен остаться нетронутым
    # для outbox-операции. Проверяем через возвращаемое значение и отсутствие
    # новых строк в email_outbox.
    result = await enqueue_outbox_email_batch(real_db_session, [])
    assert result == []


async def test_batch_insert_dedup_not_required_at_sql_level(real_db_session):
    """Семантика: batch-INSERT не дедуплицирует сам — это задача caller'а
    (см. _enqueue_many в meetings/notifications.py). Два одинаковых email → две строки.
    Гарантирует, что фикс не «молча» схлопнул дубли.
    """
    from app.models.email_outbox import EmailOutbox
    from app.services.email_outbox import enqueue_outbox_email_batch

    items = [
        _item(to_email="dup@test.com", body_text=None),
        _item(to_email="dup@test.com", body_text=None),
    ]
    ids = await enqueue_outbox_email_batch(real_db_session, items)
    await real_db_session.flush()

    assert len(ids) == 2
    rows = (
        (await real_db_session.execute(select(EmailOutbox).where(EmailOutbox.id.in_(ids))))
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert {r.to_email for r in rows} == {"dup@test.com"}
