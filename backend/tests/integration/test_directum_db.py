"""Integration-тесты модуля Directum (DSN-based, реальная PostgreSQL).

Проверяют миграцию 098 (singleton сеется), полный прогон
:func:`run_directum_sync` на реальной БД (run-строка + настоящие outbox-строки
messenger/email) и матчинг ФИО реальными SQL-условиями (ё→е, порядок слов).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.core.secret_crypto import encrypt_secret
from app.models.directum import DirectumSettings
from app.models.email_outbox import EmailOutbox
from app.models.helpdesk import MessengerOutbox
from app.models.matrix_bot import MatrixBotSettings
from app.models.user import User
from app.services.directum import sync
from app.services.directum.matcher import Matched, Unmatched, match_performer
from app.services.directum.odata import OverdueAssignment

_MOSCOW = timezone(timedelta(hours=3))


async def _mk_user(session, *, full_name: str, opt_in: bool) -> User:
    user = User(
        email=f"directum-{uuid.uuid4().hex[:8]}@portal.local",
        full_name=full_name,
        role="reader",
        auth_source="local",
        current_status="working",
        notify_email=False,
        notify_inapp=False,
        lang="ru",
        preferences={"chat_notifications_enabled": opt_in},
        updated_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    return user


def _uniq(full_name: str) -> str:
    """Уникальный суффикс в фамилии — dev-БД с реальными ~300 сотрудниками,
    «Кузьмин Александр Вадимович» без суффикса дал бы Ambiguous/чужой матч."""
    return full_name.replace(" ", f"{uuid.uuid4().hex[:4]} ", 1)


async def _load_singleton(session) -> DirectumSettings:
    row = (
        await session.execute(select(DirectumSettings).where(DirectumSettings.id == 1))
    ).scalar_one()
    return row


async def test_migration_seeds_singleton(real_db_session):
    """Сид миграции + форма колонок. Дев-БД живая (админ настраивает модуль) —
    проверяем инварианты, а не дефолты значений."""
    row = await _load_singleton(real_db_session)
    assert row is not None
    assert set(row.overdue_run_hours).issubset(set(range(24)))


async def test_sync_full_flow_creates_run_and_outbox_rows(real_db_session):
    session = real_db_session

    opted_in = await _mk_user(session, full_name=_uniq("Кузьмин Александр Вадимович"), opt_in=True)
    opted_out = await _mk_user(session, full_name=_uniq("Козлов Сергей Николаевич"), opt_in=False)

    settings = await _load_singleton(session)
    settings.enabled = True
    settings.overdue_enabled = True
    settings.auth_username = "PDC1\\svc-directum"
    settings.auth_password_enc = encrypt_secret("secret")
    settings.notify_emails = ["boss@mage.ru"]

    matrix = (
        await session.execute(select(MatrixBotSettings).where(MatrixBotSettings.id == 1))
    ).scalar_one()
    matrix.enabled = True
    matrix.access_token_enc = encrypt_secret("mct_test")
    matrix.homeserver_url = "https://matrix.mage.ru"
    matrix.server_name = "matrix.mage.ru"
    matrix.bot_user_id = "@portal-bot:matrix.mage.ru"
    await session.flush()

    now = datetime.now(_MOSCOW)
    tasks = [
        OverdueAssignment(
            id="t1",
            subject="Подпишите: соглашение",
            deadline=now - timedelta(days=10),
            performer_name=opted_in.full_name,
        ),
        OverdueAssignment(
            id="t2",
            subject="Ознакомьтесь: приказ",
            deadline=now - timedelta(days=3),
            performer_name=opted_out.full_name,
        ),
        OverdueAssignment(
            id="t3",
            subject=">> Согласуйте: заявление",
            deadline=now - timedelta(days=1),
            performer_name="Капитан судна Н.Трубятчинский",
        ),
    ]

    with patch.object(sync, "fetch_overdue_assignments", AsyncMock(return_value=tasks)):
        run = await sync.run_directum_sync(session, triggered_by="manual")

    # Run-строка: счётчики и статус (unmatched — данные, не сбой).
    assert run.status == "success"
    assert run.tasks_total == 3
    assert run.performers_total == 3
    assert run.users_notified == 1
    assert run.users_skipped_opt_in == 1
    assert run.users_unmatched == 1
    assert run.finished_at is not None
    assert run.report["unmatched"][0]["fio"] == "Капитан судна Н.Трубятчинский"

    # Messenger-outbox: один дайджест opted-in сотруднику по MXID-конвенции.
    # Скоуп по payload.directum_run_id: в живой дев-БД уже есть строки от
    # реальных прогонов админа (этот тест-прогон — свой run.id).
    mob_rows = (
        (
            await session.execute(
                select(MessengerOutbox).where(
                    MessengerOutbox.related_resource_type == "directum_run",
                    MessengerOutbox.payload["directum_run_id"].as_string() == str(run.id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(mob_rows) == 1
    expected_localpart = opted_in.email.split("@")[0].lower()
    assert mob_rows[0].chat_id == f"@{expected_localpart}:matrix.mage.ru"
    assert mob_rows[0].provider == "matrix"
    assert mob_rows[0].status == "PENDING"
    assert "Подпишите: соглашение" in mob_rows[0].text

    # Email-outbox: сводка на явного получателя (так же скоуп по run_id).
    email_rows = (
        (
            await session.execute(
                select(EmailOutbox).where(
                    EmailOutbox.kind == "directum",
                    EmailOutbox.payload["directum_run_id"].as_string() == str(run.id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(email_rows) == 1
    assert email_rows[0].to_email == "boss@mage.ru"
    assert "просроченные задачи" in email_rows[0].subject


async def test_matcher_real_fio_word_order_and_yo(real_db_session):
    session = real_db_session
    user = await _mk_user(session, full_name=_uniq("Богославский Артём Петрович"), opt_in=False)

    result = await match_performer(session, "Артем " + user.full_name.split()[0])
    assert isinstance(result, Matched)
    assert result.user.id == user.id

    result_none = await match_performer(session, "Несуществующий Человек Человекович")
    assert isinstance(result_none, Unmatched)
