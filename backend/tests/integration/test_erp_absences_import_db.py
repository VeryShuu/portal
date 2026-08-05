"""Integration-тесты импорта отсутствий ERP через реальную БД.

Ключевые сценарии (отличия от потока дней рождения):

* **Full-replace**: повторный импорт удаляет старые записи ``source='erp_sync'``
  и вставляет новые. Сотрудник, исчезнувший из файла, стирается автоматически.
* **Безопасность failed-файла**: при 0 валидных строк + ошибках парсинга
  (``status='failed'``) БД **не трогается** — старые отсутствия остаются.
* **Дедуп по ``message_id``**: повторный импорт того же письма = skip.
* **Unmatched/ambiguous** попадают в отчёт, не пишутся в БД.
* **Уведомления** (email_outbox + notifications) создаются в той же транзакции.

Требует ``INTEGRATION_DB=true`` и запущенного Postgres + Redis.
Миграция 092 должна быть применена (создаёт таблицы + колонки настроек).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models.email_outbox import EmailOutbox
from app.models.erp_sync import ErpAbsence, ErpAbsencesRun, ErpSyncSettings
from app.models.notification import Notification
from app.models.user import User
from app.services.erp_sync.absences_importer import (
    AbsenceAttachment,
    absence_attachment_hash,
    run_absences_import,
)

pytestmark = pytest.mark.asyncio

# Репрезентативный фрагмент реального файла заказчика. Содержит заголовок
# колонок, строку сотрудника и строки периодов (смешанный формат дат).
_TSV_TEMPLATE = (
    "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
    "{fio}\n"
    "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
    "Инженер\tОтдел\tБолезнь\t21.08.2026 0:00:00\t25.08.2026\n"
)


def _make_tsv(fio: str) -> bytes:
    return _TSV_TEMPLATE.replace("{fio}", fio).encode("utf-8")


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
    """Singleton уже создан миграцией 087; убедимся, что существует."""
    settings = (
        await session.execute(select(ErpSyncSettings).where(ErpSyncSettings.id == 1))
    ).scalar_one_or_none()
    if settings is None:
        settings = ErpSyncSettings(id=1)
        session.add(settings)
    await session.flush()
    return settings


async def _count_absences(session, *, user_id=None) -> int:
    q = select(ErpAbsence)
    if user_id is not None:
        q = q.where(ErpAbsence.user_id == user_id)
    return len((await session.execute(q)).scalars().all())


async def test_full_replace_inserts_and_logs(real_db_session, redis_client):
    """Полный цикл: файл → 2 периода вставлены, run создан со счётчиками."""
    admin = await _seed_user(
        real_db_session,
        full_name="Александров Александр Дмитриевич",
        email=f"abs-admin-{uuid.uuid4().hex[:8]}@portal.local",
    )
    await _seed_settings(real_db_session)
    tsv = _make_tsv("Александров Александр Дмитриевич")

    run = await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(
            filename="absences.txt", data=tsv, hash=absence_attachment_hash(tsv)
        ),
        message_id="<abs-test-1@example.com>",
        triggered_by="manual",
    )

    # 1. 2 периода отсутствий вставлены для пользователя.
    assert await _count_absences(real_db_session, user_id=admin.id) == 2

    # 2. Run записан с корректными счётчиками.
    assert run.status == "success"
    assert run.rows_matched == 2
    assert run.rows_inserted == 2
    assert run.triggered_by == "manual"
    assert run.message_id == "<abs-test-1@example.com>"

    # 3. Раздел inserted в отчёте.
    assert len(run.report["inserted"]) == 2
    inserted_kinds = sorted(i["kind"] for i in run.report["inserted"])
    assert inserted_kinds == ["sick", "vacation_main"]


async def test_full_replace_removes_old_records(real_db_session, redis_client):
    """Повторный импорт с другим файлом: старые записи стираются, новые вставляются."""
    fio = "Перезаписов Перезапис Перезаписович"
    admin = await _seed_user(
        real_db_session, full_name=fio, email=f"abs-repl-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_settings(real_db_session)

    # 1-й импорт: 2 периода.
    tsv1 = _make_tsv(fio)
    await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(
            filename="a.txt", data=tsv1, hash=absence_attachment_hash(tsv1)
        ),
        message_id="<repl-1@example.com>",
        triggered_by="cron",
    )
    assert await _count_absences(real_db_session, user_id=admin.id) == 2

    # 2-й импорт: только 1 период (другой). Старые 2 должны исчезнуть.
    tsv2 = (
        "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
        f"{fio}\n"
        "Инженер\tОтдел\tКомандировка\t01.09.2026 0:00:00\t05.09.2026\n"
    ).encode()
    run2 = await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(
            filename="a.txt", data=tsv2, hash=absence_attachment_hash(tsv2)
        ),
        message_id="<repl-2@example.com>",
        triggered_by="cron",
    )
    # Осталась ровно 1 запись (новая), 2 старых стёрты full-replace'ом.
    assert await _count_absences(real_db_session, user_id=admin.id) == 1
    assert run2.rows_inserted == 1

    # Проверим, что осталась именно командировка (новая), а не отпуск/болезнь.
    remaining = (
        (await real_db_session.execute(select(ErpAbsence).where(ErpAbsence.user_id == admin.id)))
        .scalars()
        .all()
    )
    assert remaining[0].kind == "business_trip"


async def test_full_replace_removes_disappeared_employee(real_db_session, redis_client):
    """Сотрудник исчез из файла → его отсутствия стираются автоматически."""
    fio_keep = "Оставшев Остав Оставович"
    fio_gone = "Исчезов Исчез Исчезович"
    keep = await _seed_user(
        real_db_session, full_name=fio_keep, email=f"keep-{uuid.uuid4().hex[:8]}@portal.local"
    )
    gone = await _seed_user(
        real_db_session, full_name=fio_gone, email=f"gone-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_settings(real_db_session)

    # 1-й импорт: оба сотрудника.
    tsv1 = (
        "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
        f"{fio_keep}\nИнженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
        f"{fio_gone}\nИнженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
    ).encode()
    await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(
            filename="a.txt", data=tsv1, hash=absence_attachment_hash(tsv1)
        ),
        message_id="<disp-1@example.com>",
        triggered_by="cron",
    )
    assert await _count_absences(real_db_session, user_id=gone.id) == 1

    # 2-й импорт: только fio_keep. Записи gone должны исчезнуть.
    tsv2 = (
        "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
        f"{fio_keep}\nИнженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
    ).encode()
    await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(
            filename="a.txt", data=tsv2, hash=absence_attachment_hash(tsv2)
        ),
        message_id="<disp-2@example.com>",
        triggered_by="cron",
    )
    assert await _count_absences(real_db_session, user_id=gone.id) == 0
    assert await _count_absences(real_db_session, user_id=keep.id) == 1


async def test_failed_file_does_not_wipe_db(real_db_session, redis_client):
    """Битый файл (0 валидных строк + ошибки) → status=failed, БД не трогается.

    Критичный инвариант: одно кривое письмо не должно стереть всю историю
    отсутствий. Только при наличии matched-строк делается DELETE→INSERT.
    """
    fio = "Защищён Защит Защитович"
    admin = await _seed_user(
        real_db_session, full_name=fio, email=f"safe-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_settings(real_db_session)

    # 1-й импорт: валидный, 1 период в БД.
    tsv_ok = _make_tsv(fio)
    await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(
            filename="a.txt", data=tsv_ok, hash=absence_attachment_hash(tsv_ok)
        ),
        message_id="<safe-1@example.com>",
        triggered_by="cron",
    )
    assert await _count_absences(real_db_session, user_id=admin.id) == 2

    # 2-й импорт: полностью битый файл (нет заголовка колонок → парсер молчит).
    tsv_bad = "Это не отчёт отсутствий\nСовсем другой формат\n".encode()
    run2 = await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(
            filename="a.txt", data=tsv_bad, hash=absence_attachment_hash(tsv_bad)
        ),
        message_id="<safe-2@example.com>",
        triggered_by="cron",
    )
    assert run2.status in ("failed", "skipped")
    # БД не стёрта — все 2 записи на месте. Критичный инвариант: при отсутствии
    # matched-строк DELETE не выполняется (иначе одно кривое письмо сотрёт
    # всю историю отсутствий).
    assert await _count_absences(real_db_session, user_id=admin.id) == 2


async def test_dedup_by_message_id(real_db_session, redis_client):
    """Повторный импорт того же письма (message_id) — skip, второй run не создаётся."""
    fio = "Дедупов Дедуп Дедупович"
    await _seed_user(
        real_db_session, full_name=fio, email=f"abs-dedup-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_settings(real_db_session)
    tsv = _make_tsv(fio)
    msg_id = "<abs-dedup@example.com>"
    attachment = AbsenceAttachment(filename="a.txt", data=tsv, hash=absence_attachment_hash(tsv))

    first = await run_absences_import(
        real_db_session,
        redis_client,
        attachment=attachment,
        message_id=msg_id,
        triggered_by="cron",
    )
    second = await run_absences_import(
        real_db_session,
        redis_client,
        attachment=attachment,
        message_id=msg_id,
        triggered_by="cron",
    )
    # Второй вызов вернул ту же запись (skip).
    assert second.id == first.id

    runs = (
        (
            await real_db_session.execute(
                select(ErpAbsencesRun).where(ErpAbsencesRun.message_id == msg_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(runs) == 1


async def test_unmatched_not_written(real_db_session, redis_client):
    """ФИО, которого нет на портале → unmatched, запись не создаётся."""
    await _seed_settings(real_db_session)
    tsv = _make_tsv("Несуществующий Сотрудник Совсем")

    run = await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(filename="a.txt", data=tsv, hash=absence_attachment_hash(tsv)),
        message_id=f"<unm-{uuid.uuid4().hex}@example.com>",
        triggered_by="manual",
    )
    assert run.rows_unmatched == 2  # 2 периода этого ФИО — оба unmatched
    assert run.rows_inserted == 0
    assert len(run.report["unmatched"]) == 2
    # В БД ничего не записано (нет matched).
    assert await _count_absences(real_db_session) == 0


async def test_ambiguous_not_written(real_db_session, redis_client):
    """Два пользователя с одинаковым ФИО → ambiguous, ничего не пишется."""
    fio = "Однофамилец Один Одинович"
    await _seed_user(
        real_db_session, full_name=fio, email=f"abs-amb-1-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_user(
        real_db_session, full_name=fio, email=f"abs-amb-2-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_settings(real_db_session)
    tsv = _make_tsv(fio)

    run = await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(filename="a.txt", data=tsv, hash=absence_attachment_hash(tsv)),
        message_id=f"<abs-amb-{uuid.uuid4().hex}@example.com>",
        triggered_by="manual",
    )
    assert run.rows_ambiguous == 2  # 2 периода, оба неоднозначны
    assert run.rows_inserted == 0
    assert len(run.report["ambiguous"]) == 2


async def test_creates_notifications(real_db_session, redis_client):
    """Email + in-app уведомления создаются в той же транзакции."""
    fio = "Нотифаев Нотиф Нотифович"
    await _seed_user(
        real_db_session, full_name=fio, email=f"abs-notify-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_settings(real_db_session)
    tsv = _make_tsv(fio)
    msg_id = f"<abs-notify-{uuid.uuid4().hex}@example.com>"

    run = await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(filename="a.txt", data=tsv, hash=absence_attachment_hash(tsv)),
        message_id=msg_id,
        triggered_by="cron",
    )

    # Email в outbox.
    outbox_rows = (
        (
            await real_db_session.execute(
                select(EmailOutbox).where(EmailOutbox.related_resource_type == "erp_absences_run")
            )
        )
        .scalars()
        .all()
    )
    assert any(o.payload.get("erp_absences_run_id") == run.id for o in outbox_rows)

    # In-app notification.
    notifs = (
        (
            await real_db_session.execute(
                select(Notification).where(Notification.type == "erp_absences_report")
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs) >= 1


async def test_absence_record_fields_correct(real_db_session, redis_client):
    """Поля записи ErpAbsence корректно заполнены из файла."""
    fio = "Полев Поля Полевич"
    admin = await _seed_user(
        real_db_session, full_name=fio, email=f"fields-{uuid.uuid4().hex[:8]}@portal.local"
    )
    await _seed_settings(real_db_session)
    tsv = _make_tsv(fio)

    await run_absences_import(
        real_db_session,
        redis_client,
        attachment=AbsenceAttachment(filename="a.txt", data=tsv, hash=absence_attachment_hash(tsv)),
        message_id=f"<fields-{uuid.uuid4().hex}@example.com>",
        triggered_by="cron",
    )

    vacation = (
        await real_db_session.execute(
            select(ErpAbsence)
            .where(ErpAbsence.user_id == admin.id)
            .where(ErpAbsence.kind == "vacation_main")
        )
    ).scalar_one()
    assert vacation.position == "Инженер"
    assert vacation.department == "Отдел"
    assert vacation.start_date == date(2026, 8, 10)
    assert vacation.end_date == date(2026, 8, 20)
    assert vacation.source == "erp_sync"
