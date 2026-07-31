"""Integration-тесты ERP-sync импорта через реальную БД.

Покрытие:
- :func:`run_import`: файл → пользователи обновлены (birth_date/gender),
  diff записан в ``erp_sync_runs.report``, лог создан.
- Дедуп по ``message_id``: повторный импорт того же письма = skip.
- Unmatched/ambiguous/conflicts попадают в отчёт.
- Уведомления (email_outbox + notifications) создаются в той же транзакции.

Требует ``INTEGRATION_DB=true`` и запущенного Postgres + Redis.
Миграция 087+088 должна быть применена (создаёт таблицы + singleton-настройки).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.email_outbox import EmailOutbox
from app.models.erp_sync import ErpSyncRun, ErpSyncSettings
from app.models.notification import Notification
from app.models.user import User
from app.services.erp_sync.importer import Attachment, attachment_hash, run_import

pytestmark = pytest.mark.asyncio

# Тестовый файл: 2 валидных строки (1 изменит данные, 1 идентичная текущей),
# 1 unmatched (нет такого пользователя).
_TSV = (
    "Сотрудник\tФизическое лицо.Дата рождения\tФизическое лицо.Пол\n"
    "{matched_fio}\t15.04.1988\tМужской\n"
    "{matched_fio}\t15.04.1988\tМужской\n"  # дубликат-идентичный → дедуп
    "Несуществующий Сотрудник\t01.01.1990\tЖенский\n"  # unmatched
).encode()


async def _seed_user(session, *, full_name: str, email: str) -> User:
    user = User(
        email=email,
        full_name=full_name,
        role="admin",  # admin — чтобы получить уведомление
        auth_source="local",
        password_hash="x",
        presence_status="office",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def _seed_settings(session) -> ErpSyncSettings:
    """Singleton уже создан миграцией 087; обновим на всякий случай."""
    settings = (
        await session.execute(select(ErpSyncSettings).where(ErpSyncSettings.id == 1))
    ).scalar_one_or_none()
    if settings is None:
        settings = ErpSyncSettings(id=1)
        session.add(settings)
    await session.flush()
    return settings


async def test_run_import_updates_users_and_logs(real_db_session, redis_client):
    """Полный цикл: файл → 1 пользователь обновлён, unmatched в отчёте, run создан."""
    admin = await _seed_user(
        real_db_session,
        full_name="Александров Александр Дмитриевич",
        email=f"erp-admin-{uuid.uuid4().hex[:8]}@portal.local",
    )
    await _seed_settings(real_db_session)

    tsv = _TSV.replace(b"{matched_fio}", "Александров Александр Дмитриевич".encode())

    run = await run_import(
        real_db_session,
        redis_client,
        attachment=Attachment(filename="report.tsv", data=tsv, hash=attachment_hash(tsv)),
        message_id="<test-1@example.com>",
        triggered_by="manual",
    )

    # 1. Пользователь обновлён.
    refreshed = (
        await real_db_session.execute(select(User).where(User.id == admin.id))
    ).scalar_one()
    assert refreshed.birth_date is not None
    assert refreshed.birth_date.isoformat() == "1988-04-15"
    assert refreshed.gender == "male"

    # 2. Run записан с корректными счётчиками.
    assert run.status == "partial"  # есть unmatched → partial
    assert run.rows_updated == 1
    assert run.rows_unmatched == 1
    assert run.triggered_by == "manual"
    assert run.message_id == "<test-1@example.com>"

    # 3. Diff в отчёте.
    assert len(run.report["changed"]) == 1
    assert run.report["changed"][0]["fio"] == "Александров Александр Дмитриевич"
    assert "birth_date" in run.report["changed"][0]["fields"]
    assert run.report["unmatched"][0]["fio"] == "Несуществующий Сотрудник"


async def test_run_import_dedup_by_message_id(real_db_session, redis_client):
    """Повторный импорт того же письма (message_id) — skip, второй run не создаётся."""
    await _seed_user(
        real_db_session,
        full_name="Дедупов Дедуп Дедупович",
        email=f"erp-dedup-{uuid.uuid4().hex[:8]}@portal.local",
    )
    await _seed_settings(real_db_session)
    tsv = _TSV.replace(b"{matched_fio}", "Дедупов Дедуп Дедупович".encode())
    msg_id = "<dedup-test@example.com>"
    attachment = Attachment(filename="r.tsv", data=tsv, hash=attachment_hash(tsv))

    first = await run_import(
        real_db_session,
        redis_client,
        attachment=attachment,
        message_id=msg_id,
        triggered_by="cron",
    )
    second = await run_import(
        real_db_session,
        redis_client,
        attachment=attachment,
        message_id=msg_id,
        triggered_by="cron",
    )
    # Второй вызов вернул ту же запись (skip).
    assert second.id == first.id

    # В БД только один run с этим message_id.
    runs = (
        (await real_db_session.execute(select(ErpSyncRun).where(ErpSyncRun.message_id == msg_id)))
        .scalars()
        .all()
    )
    assert len(runs) == 1


async def test_run_import_no_changes_not_counted_as_updated(real_db_session, redis_client):
    """Если данные пользователя уже совпадают — diff пустой, rows_updated=0."""
    admin = await _seed_user(
        real_db_session,
        full_name="Неизменов Неизмен Неизменович",
        email=f"erp-nochange-{uuid.uuid4().hex[:8]}@portal.local",
    )
    # Предзаполняем теми же данными, что в файле.
    from datetime import date

    admin.birth_date = date(1990, 1, 1)
    admin.gender = "male"
    await real_db_session.flush()
    await _seed_settings(real_db_session)

    tsv = ("Сотрудник\tДата\tПол\nНеизменов Неизмен Неизменович\t01.01.1990\tМужской\n").encode()

    run = await run_import(
        real_db_session,
        redis_client,
        attachment=Attachment(filename="r.tsv", data=tsv, hash=attachment_hash(tsv)),
        message_id=f"<nochange-{uuid.uuid4().hex}@example.com>",
        triggered_by="manual",
    )
    assert run.rows_matched == 1  # сопоставлен
    assert run.rows_updated == 0  # но изменений нет → не в changed
    assert run.report["changed"] == []
    assert run.status == "success"  # нет проблем


async def test_run_import_creates_notifications(real_db_session, redis_client):
    """Email + in-app уведомления создаются в той же транзакции."""
    await _seed_user(
        real_db_session,
        full_name="Нотифаев Нотиф Нотифович",
        email=f"erp-notify-{uuid.uuid4().hex[:8]}@portal.local",
    )
    await _seed_settings(real_db_session)
    tsv = ("Сотрудник\tДата\tПол\nНотифаев Нотиф Нотифович\t01.01.1990\tМужской\n").encode()

    msg_id = f"<notify-{uuid.uuid4().hex}@example.com>"
    run = await run_import(
        real_db_session,
        redis_client,
        attachment=Attachment(filename="r.tsv", data=tsv, hash=attachment_hash(tsv)),
        message_id=msg_id,
        triggered_by="cron",
    )

    # Email в outbox.
    outbox_rows = (
        (
            await real_db_session.execute(
                select(EmailOutbox).where(EmailOutbox.related_resource_type == "erp_sync_run")
            )
        )
        .scalars()
        .all()
    )
    assert any(o.payload.get("erp_sync_run_id") == run.id for o in outbox_rows)

    # In-app notification.
    notifs = (
        (
            await real_db_session.execute(
                select(Notification).where(Notification.type == "erp_sync_report")
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs) >= 1


async def test_run_import_ambiguous_not_written(real_db_session, redis_client):
    """Два пользователя с одинаковым ФИО → ambiguous, ни один не обновлён."""
    fio = "Однофамилец Один Одинович"
    await _seed_user(
        real_db_session, full_name=fio, email=f"amb-1-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_user(
        real_db_session, full_name=fio, email=f"amb-2-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_settings(real_db_session)
    tsv = (f"Сотрудник\tДата\tПол\n{fio}\t01.01.1990\tМужской\n").encode()

    run = await run_import(
        real_db_session,
        redis_client,
        attachment=Attachment(filename="r.tsv", data=tsv, hash=attachment_hash(tsv)),
        message_id=f"<amb-{uuid.uuid4().hex}@example.com>",
        triggered_by="manual",
    )
    assert run.rows_ambiguous == 1
    assert run.rows_updated == 0  # неоднозначно → не пишем
    assert len(run.report["ambiguous"]) == 1
    # 2 кандидата в отчёте.
    assert len(run.report["ambiguous"][0]["candidates"]) == 2
