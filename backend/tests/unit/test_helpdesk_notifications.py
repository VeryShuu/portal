"""Unit-тесты in-app уведомлений helpdesk (``services/helpdesk/notifications.py``).

Покрывает получателей и тип/содержимое уведомлений для всех 5 ``notify_*``:
- ``notify_ticket_created`` → все агенты с ``notify_new=True``
- ``notify_ticket_assigned`` → requester (≠actor) + assignee (≠actor)
- ``notify_agent_reply`` → requester
- ``notify_requester_reply`` → assignee (или все агенты, если не назначен)
- ``notify_status_changed`` → requester (closed → тело про reopen-окно)

``_fan_out`` мокается (он делает ``create_notification`` + commit + SSE publish),
чтобы тестировать только логику выбора получателей и формирования title/body.
``_select_agents_to_notify`` покрывается напрямую с mock-сессией.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.helpdesk import notifications as notif


def _ticket(
    *,
    number: int = 42,
    subject: str = "Тема заявки",
    requester_user_id: uuid.UUID | None = None,
    assignee_user_id: uuid.UUID | None = None,
    requester_name: str | None = None,
    requester_email: str | None = None,
    source: str = "web",
) -> SimpleNamespace:
    """Билет как SimpleNamespace с ``ticket_number`` property-эмуляцией."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        number=number,
        ticket_number=f"TKT-{number}",
        subject=subject,
        requester_user_id=requester_user_id,
        assignee_user_id=assignee_user_id,
        requester_name=requester_name,
        requester_email=requester_email,
        source=source,
    )


def _user(*, uid: uuid.UUID | None = None, full_name: str = "Агент") -> SimpleNamespace:
    return SimpleNamespace(id=uid or uuid.uuid4(), full_name=full_name)


def _fake_redis() -> MagicMock:
    return MagicMock()


# ── _select_agents_to_notify ────────────────────────────────────────────────


def _db_returning_agent_ids(agent_ids: list[uuid.UUID]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=agent_ids)))
    db.execute = AsyncMock(return_value=result)
    return db


class TestSelectAgentsToNotify:
    @pytest.mark.asyncio
    async def test_returns_all_agents(self):
        a1, a2 = uuid.uuid4(), uuid.uuid4()
        db = _db_returning_agent_ids([a1, a2])
        out = await notif._select_agents_to_notify(db)
        assert out == [a1, a2]

    @pytest.mark.asyncio
    async def test_excludes_user(self):
        a1, excluded = uuid.uuid4(), uuid.uuid4()
        db = _db_returning_agent_ids([a1])
        out = await notif._select_agents_to_notify(db, exclude_user_id=excluded)
        assert excluded not in out

    @pytest.mark.asyncio
    async def test_require_notify_new_default_true(self):
        """По умолчанию ``require_notify_new=True`` — фильтр активен."""
        a1 = uuid.uuid4()
        db = _db_returning_agent_ids([a1])
        out = await notif._select_agents_to_notify(db)
        assert out == [a1]
        db.execute.assert_awaited_once()


# ── notify_ticket_created → все агенты с notify_new ─────────────────────────


class TestNotifyTicketCreated:
    @pytest.mark.asyncio
    async def test_fans_out_to_agents(self):
        a1, a2 = uuid.uuid4(), uuid.uuid4()
        db = _db_returning_agent_ids([a1, a2])
        redis = _fake_redis()
        ticket = _ticket(number=10)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=2)) as fan:
            sent = await notif.notify_ticket_created(db, redis, ticket=ticket)

        assert sent == 2
        fan.assert_awaited_once()
        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [a1, a2]
        assert kwargs["type_"] == "helpdesk_ticket_created"
        assert "TKT-10" in kwargs["title"]
        assert kwargs["body"] == ticket.subject
        assert kwargs["link"] == f"/helpdesk/tickets/{ticket.id}"


# ── notify_ticket_assigned → requester(≠actor) + assignee(≠actor) ──────────


class TestNotifyTicketAssigned:
    @pytest.mark.asyncio
    async def test_notifies_requester_and_assignee_excluding_actor(self):
        actor = _user()
        requester = uuid.uuid4()
        assignee = _user(full_name="Мария")
        ticket = _ticket(requester_user_id=requester)
        db, redis = MagicMock(), _fake_redis()

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=2)) as fan:
            sent = await notif.notify_ticket_assigned(
                db, redis, ticket=ticket, assignee=assignee, actor=actor
            )

        assert sent == 2
        kwargs = fan.await_args.kwargs
        assert requester in kwargs["user_ids"]
        assert assignee.id in kwargs["user_ids"]
        assert actor.id not in kwargs["user_ids"]
        assert "Мария" in kwargs["body"]
        assert kwargs["link"] == f"/helpdesk/my/{ticket.id}"

    @pytest.mark.asyncio
    async def test_actor_is_assignee_excludes_self(self):
        """Агент берёт тикет сам → уведомляется только requester (assignee=actor)."""
        requester = uuid.uuid4()
        actor = _user(full_name="Сам взял")
        ticket = _ticket(requester_user_id=requester)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=1)) as fan:
            await notif.notify_ticket_assigned(
                MagicMock(), _fake_redis(), ticket=ticket, assignee=actor, actor=actor
            )

        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [requester]

    @pytest.mark.asyncio
    async def test_no_requester_and_actor_is_assignee_empty_targets(self):
        """Нет requester и assignee=actor → пустой список получателей (0 отправлено)."""
        actor = _user()
        ticket = _ticket(requester_user_id=None)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=0)) as fan:
            sent = await notif.notify_ticket_assigned(
                MagicMock(), _fake_redis(), ticket=ticket, assignee=actor, actor=actor
            )

        assert sent == 0
        assert fan.await_args.kwargs["user_ids"] == []


# ── notify_agent_reply → requester ──────────────────────────────────────────


class TestNotifyAgentReply:
    @pytest.mark.asyncio
    async def test_notifies_requester(self):
        requester = uuid.uuid4()
        ticket = _ticket(requester_user_id=requester)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=1)) as fan:
            sent = await notif.notify_agent_reply(
                MagicMock(), _fake_redis(), ticket=ticket, body_preview="ответ агент"
            )

        assert sent == 1
        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [requester]
        assert kwargs["type_"] == "helpdesk_agent_reply"
        assert kwargs["body"] == "ответ агент"

    @pytest.mark.asyncio
    async def test_no_requester_zero_sent(self):
        ticket = _ticket(requester_user_id=None)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=0)) as fan:
            sent = await notif.notify_agent_reply(
                MagicMock(), _fake_redis(), ticket=ticket, body_preview="x"
            )

        assert sent == 0
        assert fan.await_args.kwargs["user_ids"] == []


# ── notify_requester_reply → assignee или все агенты ────────────────────────


class TestNotifyRequesterReply:
    @pytest.mark.asyncio
    async def test_assigned_ticket_notifies_assignee_only(self):
        assignee = uuid.uuid4()
        ticket = _ticket(assignee_user_id=assignee)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=1)) as fan:
            await notif.notify_requester_reply(
                MagicMock(), _fake_redis(), ticket=ticket, body_preview="дополнение"
            )

        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [assignee]

    @pytest.mark.asyncio
    async def test_unassigned_ticket_notifies_all_agents(self):
        """Нет assignee → все агенты (require_notify_new=False)."""
        a1, a2 = uuid.uuid4(), uuid.uuid4()
        ticket = _ticket(assignee_user_id=None)
        db = _db_returning_agent_ids([a1, a2])

        with (
            patch.object(notif, "_fan_out", new=AsyncMock(return_value=2)) as fan,
        ):
            await notif.notify_requester_reply(
                db, _fake_redis(), ticket=ticket, body_preview="новое сообщение"
            )

        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [a1, a2]
        assert kwargs["type_"] == "helpdesk_requester_reply"
        assert kwargs["link"] == f"/helpdesk/tickets/{ticket.id}"


# ── notify_status_changed → closed добавляет reopen-окно в body ─────────────


class TestNotifyStatusChanged:
    @pytest.mark.asyncio
    async def test_closed_includes_reopen_window(self):
        requester = uuid.uuid4()
        ticket = _ticket(requester_user_id=requester)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=1)) as fan:
            await notif.notify_status_changed(
                MagicMock(), _fake_redis(), ticket=ticket, new_status="closed"
            )

        kwargs = fan.await_args.kwargs
        assert kwargs["body"] is not None
        assert "7" in kwargs["body"]  # HELPDESK_REOPEN_WINDOW_DAYS=7

    @pytest.mark.asyncio
    async def test_no_requester_zero_sent(self):
        ticket = _ticket(requester_user_id=None)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=0)):
            sent = await notif.notify_status_changed(
                MagicMock(), _fake_redis(), ticket=ticket, new_status="closed"
            )

        assert sent == 0


# ── _fan_out → транзакционная дисциплина (commit до SSE publish) ────────────


class TestFanOut:
    @pytest.mark.asyncio
    async def test_commits_before_publish_and_returns_count(self):
        """Контракт: create_notification → commit → publish (SSE после commit)."""
        from app.services.helpdesk import notifications as notif_mod

        u1, u2 = uuid.uuid4(), uuid.uuid4()
        publish1, publish2 = AsyncMock(), AsyncMock()
        db = MagicMock()
        db.commit = AsyncMock()
        redis = _fake_redis()

        with patch.object(
            notif_mod,
            "create_notification",
            new=AsyncMock(side_effect=[publish1, publish2]),
        ):
            sent = await notif_mod._fan_out(
                db,
                redis,
                user_ids=[u1, u2],
                type_="x",
                title="t",
                body="b",
                link=None,
            )

        assert sent == 2
        db.commit.assert_awaited_once()
        # Publish callbacks вызваны после commit.
        publish1.assert_awaited_once()
        publish2.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_user_ids_zero_sent(self):
        db = MagicMock()
        db.commit = AsyncMock()

        sent = await notif._fan_out(
            db, _fake_redis(), user_ids=[], type_="x", title="t", body=None, link=None
        )

        assert sent == 0
        db.commit.assert_awaited_once()  # commit всё равно выполняется


# ── Email-уведомление агентам о новой заявке ─────────────────────────────────


def _agent_user(
    *,
    uid: uuid.UUID | None = None,
    email: str = "agent@company.local",
    notify_email: bool = True,
) -> SimpleNamespace:
    """Агент как User-заглушка (нужен id+email+notify_email для enqueue)."""
    return SimpleNamespace(
        id=uid or uuid.uuid4(), email=email, full_name="Агент", notify_email=notify_email
    )


def _first_message(
    *,
    text: str = "Текст заявки",
    html: str | None = None,
    mid: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(id=mid or uuid.uuid4(), body_text=text, body_html=html)


def _requester_user(
    *,
    full_name: str = "Иван Петров",
    email: str = "ivan@company.local",
    phone: str | None = "12-34",
    mobile: str | None = "+7 999 111-22-33",
    city: str | None = "Мурманск",
) -> SimpleNamespace:
    """Модель User-заявителя (контакты берутся из неё, как в карточке тикета)."""
    attrs: dict[str, Any] = {}
    if mobile:
        attrs["mobile"] = mobile
    if city:
        attrs["city"] = city
    return SimpleNamespace(full_name=full_name, email=email, phone=phone, attributes=attrs)


def _db_returning_agents(agents: list) -> MagicMock:
    """Заглушка сессии: ``await db.execute(...)`` → ``.scalars().all() == agents``."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = agents
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _patch_resolve_requester(requester: object | None) -> Any:
    """Мок local-import ``resolve_requester_user`` (импортируется внутри
    ``notify_ticket_created_email`` из ``app.services.helpdesk.tickets``)."""
    return patch(
        "app.services.helpdesk.tickets.resolve_requester_user",
        new=AsyncMock(return_value=requester),
    )


def _patch_load_messages(messages: list) -> Any:
    """Мок ``_load_ticket_messages_with_attachments`` — грузит сообщения тикета
    для сборки истории письма (симметрично ``enqueue_reply_outbound``). Пустой
    список → истории нет (первый ответ заявителя)."""
    return patch.object(
        notif,
        "_load_ticket_messages_with_attachments",
        new=AsyncMock(return_value=messages),
    )


class TestNotifyTicketCreatedEmail:
    """``notify_ticket_created_email`` — отправка email-уведомления всем агентам
    (notify_new + notify_email) о новой заявке через outbox ``kind=generic``."""

    @pytest.mark.asyncio
    async def test_enqueues_one_email_per_agent(self):
        a1, a2 = _agent_user(email="a1@c.local"), _agent_user(email="a2@c.local")
        db = _db_returning_agents([a1, a2])
        ticket = _ticket(number=5, subject="Тема")
        first_msg = _first_message()

        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            sent = await notif.notify_ticket_created_email(
                db, ticket=ticket, first_message=first_msg
            )

        assert sent == 2
        assert enqueue.await_count == 2
        # Первый аргумент каждого вызова — db, kw to_email = email агента.
        tos = [call.kwargs["to_email"] for call in enqueue.await_args_list]
        assert "a1@c.local" in tos
        assert "a2@c.local" in tos

    @pytest.mark.asyncio
    async def test_uses_generic_kind(self):
        """Outbox kind=generic (не helpdesk): уведомление не входит в email-тред
        тикета, не требует настроенного mailbox, работает в web-only."""
        db = _db_returning_agents([_agent_user()])
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_email(
                db, ticket=_ticket(), first_message=_first_message()
            )
        assert enqueue.await_args.kwargs["kind"] == "generic"

    @pytest.mark.asyncio
    async def test_payload_has_ticket_number_for_image_embedding(self):
        """``payload.ticket_number`` — маркер + путь к картинкам для воркера.

        Generic-уведомление (``kind=generic``) не проходит через
        ``_build_helpdesk_mime``, где CID-встраивание уже сделано. Чтобы картинки
        заявки всё же встраивались (а не отдавали 401 на ``/attachments/{id}``
        в почтовом клиенте без cookie), ``process_email_outbox`` ищет связку
        ``smtp_source=helpdesk`` + ``ticket_number`` и прогоняет body_html через
        ``_embed_helpdesk_images_into_generic``. Сводка (digest) ``ticket_number``
        не ставит → преобработка её пропускает.
        """
        db = _db_returning_agents([_agent_user()])
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_email(
                db, ticket=_ticket(number=42, subject="Тема"), first_message=_first_message()
            )
        payload = enqueue.await_args.kwargs["payload"]
        assert payload["smtp_source"] == "helpdesk"
        assert payload["ticket_number"] == 42

    @pytest.mark.asyncio
    async def test_subject_has_ticket_token(self):
        db = _db_returning_agents([_agent_user()])
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_email(
                db, ticket=_ticket(number=77, subject="Тема"), first_message=_first_message()
            )
        subject = enqueue.await_args.kwargs["subject"]
        assert "[#TKT-77]" in subject
        assert "Новая заявка" in subject

    @pytest.mark.asyncio
    async def test_bodies_built_from_template(self):
        """Тела письма строятся через ``render_new_ticket_agent_email`` — содержат
        текст заявки и номер тикета."""
        db = _db_returning_agents([_agent_user()])
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_email(
                db,
                ticket=_ticket(number=3, subject="VPN"),
                first_message=_first_message(text="Не работает интернет"),
            )
        kwargs = enqueue.await_args.kwargs
        assert "TKT-3" in kwargs["body_text"]
        assert "Не работает интернет" in kwargs["body_text"]
        # В HTML шапке номер выводится как «#3» (единый стиль helpdesk-писем).
        assert "#3 —" in kwargs["body_html"]

    @pytest.mark.asyncio
    async def test_requester_contacts_in_bodies(self):
        """Контакты заявителя (ФИО/почта/телефон/внутренний) из User попадают в
        тело письма — агент видит, как связаться с заявителем."""
        db = _db_returning_agents([_agent_user()])
        requester = _requester_user(
            full_name="Третьякова Виктория Юрьевна",
            email="tretyakova.vu@mage.ru",
            phone="55-66",
            mobile="+7 999 123-45-67",
        )
        with (
            _patch_resolve_requester(requester),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_email(
                db, ticket=_ticket(), first_message=_first_message()
            )
        kwargs = enqueue.await_args.kwargs
        for needle in (
            "Третьякова Виктория Юрьевна",
            "tretyakova.vu@mage.ru",
            "+7 999 123-45-67",
            "55-66",
        ):
            assert needle in kwargs["body_text"]
            assert needle in kwargs["body_html"]

    @pytest.mark.asyncio
    async def test_guest_requester_falls_back_to_ticket_snapshot(self):
        """Гостевая заявка без аккаунта (resolve_requester_user → None) → имя/email
        берутся из снимка тикета, телефонов нет."""
        db = _db_returning_agents([_agent_user()])
        with (
            _patch_resolve_requester(None),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_email(
                db,
                ticket=_ticket(requester_name="Гость", requester_email="guest@x.test"),
                first_message=_first_message(),
            )
        kwargs = enqueue.await_args.kwargs
        assert "Гость" in kwargs["body_text"]
        assert "guest@x.test" in kwargs["body_text"]

    @pytest.mark.asyncio
    async def test_commits_after_enqueuing(self):
        """Единый commit после всех outbox-записей (по образцу ``send_digests``)."""
        db = _db_returning_agents([_agent_user(), _agent_user()])
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()),
        ):
            await notif.notify_ticket_created_email(
                db, ticket=_ticket(), first_message=_first_message()
            )
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_agents_zero_sent(self):
        """Нет агентов с notify_new+notify_email → 0 писем, resolve_requester_user
        не вызывается (early return), commit не вызывается (как в ``send_digests``)."""
        db = _db_returning_agents([])
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            sent = await notif.notify_ticket_created_email(
                db, ticket=_ticket(), first_message=_first_message()
            )
        assert sent == 0
        enqueue.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_related_resource_is_ticket(self):
        db = _db_returning_agents([_agent_user()])
        ticket = _ticket()
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_email(
                db, ticket=ticket, first_message=_first_message()
            )
        kwargs = enqueue.await_args.kwargs
        assert kwargs["related_resource_type"] == "helpdesk_ticket"
        assert kwargs["related_resource_id"] == ticket.id


# ── Email-уведомление агенту о новом сообщении от заявителя ─────────────────


def _patch_load_user(user: object | None) -> Any:
    """Мок local-import ``load_user`` (импортируется внутри
    ``notify_requester_reply_email`` из ``app.services.helpdesk.outbound``)."""
    return patch(
        "app.services.helpdesk.outbound.load_user",
        new=AsyncMock(return_value=user),
    )


class TestNotifyRequesterReplyEmail:
    """``notify_requester_reply_email`` — email-зеркало in-app
    ``notify_requester_reply``: assignee (если назначен) или все агенты.

    Письмо несёт историю переписки после нового ответа заявителя
    (симметрично ``enqueue_reply_outbound`` для инициатора). ``_patch_load_messages``
    мокает загрузку сообщений для истории (пустой список → истории нет)."""

    @pytest.mark.asyncio
    async def test_assigned_ticket_emails_only_assignee(self):
        """Тикет назначен → 1 письмо на assignee, агенты не опрашиваются."""
        assignee = _agent_user(email="assignee@c.local")
        ticket = _ticket(number=5, subject="Тема", assignee_user_id=assignee.id)
        db = _db_returning_agents([])  # не должно зваться

        with (
            _patch_load_user(assignee),
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            sent = await notif.notify_requester_reply_email(
                db, ticket=ticket, message=_first_message()
            )

        assert sent == 1
        assert enqueue.await_count == 1
        assert enqueue.await_args.kwargs["to_email"] == "assignee@c.local"
        # При назначенном assignee список агентов не грузится.
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unassigned_ticket_emails_all_agents(self):
        """Тикет не назначен → письма всем агентам (как «новая заявка»)."""
        a1, a2 = _agent_user(email="a1@c.local"), _agent_user(email="a2@c.local")
        db = _db_returning_agents([a1, a2])
        ticket = _ticket(number=6, assignee_user_id=None)

        with (
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            sent = await notif.notify_requester_reply_email(
                db, ticket=ticket, message=_first_message()
            )

        assert sent == 2
        tos = [call.kwargs["to_email"] for call in enqueue.await_args_list]
        assert {"a1@c.local", "a2@c.local"} == set(tos)

    @pytest.mark.asyncio
    async def test_assignee_with_notify_email_false_sends_nothing(self):
        """Consent: assignee отключил email-уведомления → 0 писем, commit не зовётся."""
        assignee = SimpleNamespace(id=uuid.uuid4(), email="mute@c.local", notify_email=False)
        ticket = _ticket(assignee_user_id=assignee.id)
        db = _db_returning_agents([])

        with (
            _patch_load_user(assignee),
            _patch_load_messages([]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            sent = await notif.notify_requester_reply_email(
                db, ticket=ticket, message=_first_message()
            )

        assert sent == 0
        enqueue.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unassigned_no_agents_zero_sent(self):
        """Не назначан + нет агентов с notify_email+notify_new → 0 писем."""
        db = _db_returning_agents([])
        ticket = _ticket(assignee_user_id=None)

        with (
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            sent = await notif.notify_requester_reply_email(
                db, ticket=ticket, message=_first_message()
            )

        assert sent == 0
        enqueue.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_payload_has_ticket_number_for_image_embedding(self):
        """``payload.smtp_source=helpdesk`` + ``ticket_number`` — маркер для воркера
        на встраивание inline-картинок ответа (как в «новой заявке»)."""
        a = _agent_user()
        db = _db_returning_agents([a])
        ticket = _ticket(number=42, assignee_user_id=None)

        with (
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_requester_reply_email(db, ticket=ticket, message=_first_message())
        payload = enqueue.await_args.kwargs["payload"]
        assert payload["smtp_source"] == "helpdesk"
        assert payload["ticket_number"] == 42

    @pytest.mark.asyncio
    async def test_uses_generic_kind(self):
        a = _agent_user()
        db = _db_returning_agents([a])
        with (
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_requester_reply_email(
                db, ticket=_ticket(assignee_user_id=None), message=_first_message()
            )
        assert enqueue.await_args.kwargs["kind"] == "generic"

    @pytest.mark.asyncio
    async def test_subject_has_ticket_token(self):
        a = _agent_user()
        db = _db_returning_agents([a])
        with (
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_requester_reply_email(
                db, ticket=_ticket(number=77, subject="Тема"), message=_first_message()
            )
        subject = enqueue.await_args.kwargs["subject"]
        assert "[#TKT-77]" in subject
        assert "Новое сообщение" in subject

    @pytest.mark.asyncio
    async def test_commits_after_enqueuing(self):
        a1, a2 = _agent_user(), _agent_user()
        db = _db_returning_agents([a1, a2])
        with (
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()),
        ):
            await notif.notify_requester_reply_email(
                db, ticket=_ticket(assignee_user_id=None), message=_first_message()
            )
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_body_includes_thread_history_when_prior_messages(self):
        """С предшествующими сообщениями → письмо несёт историю переписки
        (симметрично ``enqueue_reply_outbound`` для инициатора)."""
        a = _agent_user()
        db = _db_returning_agents([a])
        ticket = _ticket(number=55, assignee_user_id=None)
        # Одно предшествующее сообщение от агента (история после нового ответа).
        prior = SimpleNamespace(
            id=uuid.uuid4(),
            body_text="Предыдущий ответ агента",
            body_html=None,
            direction="outbound",
            author_name="Агент Иванов",
            author_email="agent@c.local",
            created_at=datetime(2026, 7, 1, 9, 0),
            attachments=[],
        )

        with (
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([prior]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_requester_reply_email(
                db,
                ticket=ticket,
                message=_first_message(text="Новый ответ заявителя"),
            )

        body_html = enqueue.await_args.kwargs["body_html"]
        body_text = enqueue.await_args.kwargs["body_text"]
        # Новый ответ заявителя присутствует (наверху письма).
        assert "Новый ответ заявителя" in body_html
        assert "Новый ответ заявителя" in body_text
        # История предшествующего сообщения присутствует (после нового ответа).
        assert "Предыдущий ответ агента" in body_html
        assert "Предыдущий ответ агента" in body_text

    @pytest.mark.asyncio
    async def test_history_excludes_current_message(self):
        """``build_thread_history(exclude_id=message.id)`` — текущий ответ заявителя
        не дублируется в блоке истории (он уже наверху письма)."""
        a = _agent_user()
        db = _db_returning_agents([a])
        ticket = _ticket(number=56, assignee_user_id=None)
        current = _first_message(text="Мой новый ответ")
        # Симулируем, что текущее сообщение уже в БД (как после flush в ingress) —
        # ``_load_ticket_messages`` вернёт его, но ``exclude_id`` должен убрать.
        with (
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([current]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_requester_reply_email(db, ticket=ticket, message=current)

        body_text = enqueue.await_args.kwargs["body_text"]
        # Ответ присутствует ровно один раз (в блоке нового ответа, не в истории).
        assert body_text.count("Мой новый ответ") == 1

    @pytest.mark.asyncio
    async def test_first_reply_no_history_section(self):
        """Первый ответ заявителя (нет предшествующих сообщений) → блок истории
        пустой, письмо остаётся как раньше (без разделителя истории)."""
        a = _agent_user()
        db = _db_returning_agents([a])
        ticket = _ticket(number=57, assignee_user_id=None)

        with (
            _patch_resolve_requester(_requester_user()),
            _patch_load_messages([]),
            patch.object(notif, "enqueue_outbox_email", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_requester_reply_email(
                db, ticket=ticket, message=_first_message(text="Первый ответ")
            )

        body_text = enqueue.await_args.kwargs["body_text"]
        # Нет заголовка истории из ``_history_header_plain``.
        assert "История заявки" not in body_text


class TestBuildRequesterReplyAgentSubject:
    def test_has_ticket_token_and_subject(self):
        ticket = _ticket(number=42, subject="Не работает 1С")
        subject = notif.build_requester_reply_agent_subject(ticket)
        assert "[#TKT-42]" in subject
        assert "Новое сообщение" in subject
        assert "Не работает 1С" in subject


class TestBuildNewTicketAgentSubject:
    def test_has_ticket_token_and_subject(self):
        ticket = _ticket(number=42, subject="Сломался принтер")
        subject = notif.build_new_ticket_agent_subject(ticket)
        assert "[#TKT-42]" in subject
        assert "Новая заявка" in subject
        assert "Сломался принтер" in subject


# ── MAX-messenger уведомление о новой заявке ─────────────────────────────────


def _db_with_max_settings(settings_row: object | None) -> MagicMock:
    """Заглушка сессии: первый execute возвращает HelpdeskMaxBotSettings (через
    ``.scalars().one_or_none()``), последующие — для enqueue."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.one_or_none.return_value = settings_row
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _max_settings(*, enabled=True, token_enc="enc-token", chat_id="-100123456"):
    return SimpleNamespace(
        enabled=enabled,
        bot_token_enc=token_enc,
        chat_id=chat_id,
    )


class TestNotifyTicketCreatedMax:
    """``notify_ticket_created_max`` — отправка MAX-messenger уведомления в общий
    чат о новой заявке через ``messenger_outbox`` (provider='max')."""

    @pytest.mark.asyncio
    async def test_disabled_returns_zero(self):
        """MAX выключен → graceful no-op, no enqueue, no commit."""
        db = _db_with_max_settings(_max_settings(enabled=False))
        ticket = _ticket(number=5, subject="Тема")
        with patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue:
            sent = await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message()
            )
        assert sent == 0
        enqueue.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_settings_row_returns_zero(self):
        db = _db_with_max_settings(None)
        ticket = _ticket(number=5, subject="Тема")
        with patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue:
            sent = await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message()
            )
        assert sent == 0
        enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_misconfigured_returns_zero(self):
        """enabled=True, но нет токена/chat_id → no-op (защита от ручного
        редактирования БД)."""
        db = _db_with_max_settings(_max_settings(enabled=True, token_enc=None))
        ticket = _ticket(number=5, subject="Тема")
        with patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue:
            sent = await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message()
            )
        assert sent == 0
        enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enabled_enqueues_one_message(self):
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=77, subject="Принтер не работает")
        with (
            _patch_resolve_requester(_requester_user(full_name="Иван Петров")),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            sent = await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message(text="Сломался")
            )
        assert sent == 1
        enqueue.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_max_provider_and_chat_id(self):
        db = _db_with_max_settings(_max_settings(chat_id="-100"))
        ticket = _ticket(number=1)
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        kwargs = enqueue.await_args.kwargs
        assert kwargs["provider"] == "max"
        assert kwargs["chat_id"] == "-100"

    @pytest.mark.asyncio
    async def test_text_contains_ticket_number_and_subject(self):
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=88, subject="Не работает VPN")
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
            # URL проходит валидацию MAX → № тикета уходит в inline-кнопку, а не в текст.
            patch.object(notif, "_build_ticket_url", return_value="https://portal.example.com/x"),
        ):
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message(text="Подключиться не могу")
            )
        text = enqueue.await_args.kwargs["text"]
        # № тикета НЕ в тексте — он переехал в inline-кнопку.
        assert "#TKT-88" not in text
        # Но тема и превью остаются.
        assert "Не работает VPN" in text
        assert "Подключиться не могу" in text

    @pytest.mark.asyncio
    async def test_text_contains_requester_label(self):
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1, source="email")
        with (
            _patch_resolve_requester(_requester_user(full_name="Пётр Сидоров")),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        text = enqueue.await_args.kwargs["text"]
        # ФИО заявителя ушёл в заголовок «Заявка от ...».
        assert "Пётр Сидоров" in text
        # Поля «Источник» больше нет в шаблоне (убрано по ТЗ от 20.07.2026).
        assert "Источник" not in text

    @pytest.mark.asyncio
    async def test_text_has_requester_city_from_profile(self):
        """Город заявителя берётся из ``users.attributes['city']`` и попадает
        в отдельную строку с жирным лейблом «Город:»."""
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1)
        with (
            _patch_resolve_requester(_requester_user(city="Мурманск")),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        text = enqueue.await_args.kwargs["text"]
        assert "**Город:** Мурманск" in text

    @pytest.mark.asyncio
    async def test_text_shows_dash_when_city_missing(self):
        """Если у заявителя нет города (атрибут отсутствует) — показываем
        прочерк «Город: —», не пропускаем поле."""
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1)
        with (
            _patch_resolve_requester(_requester_user(city=None)),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        text = enqueue.await_args.kwargs["text"]
        assert "**Город:** —" in text

    @pytest.mark.asyncio
    async def test_text_shows_dash_when_guest_no_account(self):
        """Гость без аккаунта (requester=None) → нет attributes → «Город: —»."""
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1, requester_email="guest@external.com")
        with (
            _patch_resolve_requester(None),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        text = enqueue.await_args.kwargs["text"]
        assert "**Город:** —" in text

    @pytest.mark.asyncio
    async def test_template_uses_bold_labels_and_requester_in_header(self):
        """Шаблон MAX-уведомления (ТЗ от 20.07.2026):

            **Заявка от <ФИО>**
            **Город:** ...

            **Тема:** ...
            **Текст заявки:**
            <превью>

        Поля «Источник» больше нет (убрано по ТЗ). Между «Город» и «Тема» —
        пустая строка-разделитель. Лейблы и заголовок выделены ``**bold**``
        (markdown). № тикета в тексте НЕ присутствует — он переезжает в
        inline-кнопку «Открыть заявку #TKT-N».
        """
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=42, subject="Сломалась почта")
        with (
            _patch_resolve_requester(_requester_user(full_name="Иван Петров", city="Москва")),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
            # URL проходит валидацию MAX → № тикета уходит в inline-кнопку, а не в текст.
            patch.object(notif, "_build_ticket_url", return_value="https://portal.example.com/x"),
        ):
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message(text="Не приходит почта")
            )
        text = enqueue.await_args.kwargs["text"]
        # Заголовок: «Заявка от ФИО» — bold. БЕЗ эмодзи 🆕, БЕЗ № тикета, БЕЗ «Новая».
        assert "**Заявка от Иван Петров**" in text
        assert "🆕" not in text
        assert "#TKT-42" not in text
        # Лейблы — bold (markdown **).
        assert "**Город:** Москва" in text
        assert "**Тема:** Сломалась почта" in text
        assert "**Текст заявки:**" in text
        # Поля «Источник» больше нет в шаблоне.
        assert "Источник" not in text
        # Между «Город» и «Тема» — пустая строка (визуальный разделитель).
        assert "**Город:** Москва\n\n**Тема:**" in text
        # Старый формат «Заявитель:» больше не используется (ФИО ушёл в заголовок).
        assert "Заявитель:" not in text
        # Превью тела — на отдельной строке после «**Текст заявки:**».
        assert "Не приходит почта" in text

    @pytest.mark.asyncio
    async def test_payload_has_inline_keyboard_with_portal_url(self):
        """Payload включает attachments с inline_keyboard — кнопка-ссылка ведёт
        на карточку тикета (когда URL проходит валидацию MAX).

        Формат MAX (см. ``max-bot-api-client-ts/src/.../attachment.ts``):
        ``payload.buttons`` (НЕ ``rows``) — массив строк, каждая строка — массив
        кнопок. Кнопка-ссылка: ``{"type": "link", "text", "url"}``.

        MAX валидирует домен URL в кнопках строже, чем в markdown-тексте
        (отклоняет ``.local``/``localhost``/special-use TLD с 400 permanent).
        Поэтому для public-URL используется inline-кнопка, для приватного домена
        — markdown-ссылка в теле (см. ``test_fallback_to_markdown_for_local_url``).
        """
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=99)
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
            patch.object(
                notif,
                "_build_ticket_url",
                return_value="https://portal.example.com/helpdesk/tickets/x",
            ),
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        payload = enqueue.await_args.kwargs["payload"]
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        kb = payload["attachments"][0]
        assert kb["type"] == "inline_keyboard"
        # Ключевое поле MAX — ``buttons``, не ``rows``.
        assert "buttons" in kb["payload"]
        assert "rows" not in kb["payload"]
        button = kb["payload"]["buttons"][0][0]
        assert button["type"] == "link"
        # Текст кнопки включает № тикета («Открыть заявку #TKT-99»).
        assert button["text"] == "Открыть заявку #TKT-99"
        assert button["url"] == "https://portal.example.com/helpdesk/tickets/x"
        # Markdown-ссылка НЕ дублируется в тексте — только кнопка.
        assert "🔗" not in enqueue.await_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_fallback_to_markdown_for_local_url(self):
        """Если URL не проходит валидацию MAX (``.local`` / ``localhost`` /
        special-use TLD) — ссылка вставляется в тело как markdown, а inline-
        кнопка не передаётся.

        Это корень проблемы интранет-порталов: ``portal_base_url=https://portal.local``
        отклоняется MAX-кнопкой с 400 permanent (DLQ без ретраев). Markdown-ссылка
        в теле работает с любым доменом.
        """
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=99)
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
            patch.object(
                notif, "_build_ticket_url", return_value="https://portal.local/helpdesk/tickets/x"
            ),
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        kwargs = enqueue.await_args.kwargs
        # Нет inline_keyboard-attachments — иначе MAX упадёт с 400 permanent.
        assert kwargs["payload"]["attachments"] == []
        # Ссылка вставлена в текст как markdown, с № тикета.
        assert (
            "[🔗 Открыть заявку #TKT-99](https://portal.local/helpdesk/tickets/x)" in kwargs["text"]
        )

    @pytest.mark.asyncio
    async def test_related_resource_is_ticket(self):
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=42)
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        kwargs = enqueue.await_args.kwargs
        assert kwargs["related_resource_type"] == "helpdesk_ticket"
        assert kwargs["related_resource_id"] == ticket.id

    @pytest.mark.asyncio
    async def test_guest_requester_uses_ticket_snapshot(self):
        """Если ``resolve_requester_user`` возвращает None (гость без аккаунта),
        подпись заявителя берётся из снимка тикета (requester_email/name)."""
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(
            number=11,
            requester_email="guest@external.com",
            requester_name="Гость",
        )
        with (
            _patch_resolve_requester(None),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        text = enqueue.await_args.kwargs["text"]
        assert "guest@external.com" in text

    @pytest.mark.asyncio
    async def test_long_body_preview_is_truncated(self):
        """Превью длинного текста обрезается (501+ символов → многоточие)."""
        long_text = "а" * 800
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1)
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message(text=long_text)
            )
        text = enqueue.await_args.kwargs["text"]
        # Превью — это строка из «а» (возможно с «…»), длина ≤ 501 (500 + «…»).
        # Не используем ``split("\n")[-1]``: при fallback на markdown-ссылку
        # последняя строка может быть ссылкой, а не превью.
        preview_line = next(
            (line for line in text.split("\n") if line and line[0] == "а"),
            None,
        )
        assert preview_line is not None
        assert len(preview_line) <= 501
        assert preview_line.endswith("…")

    @pytest.mark.asyncio
    async def test_empty_body_preview_omits_text_section(self):
        """``first_message.body_text`` пустой/None → превью опускается
        (ветка ``if body_preview`` пропускается). За лейблом «**Текст заявки:**»
        идёт пустая строка, а не строка превью."""
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1, subject="Пустое тело")
        # URL-патч делает ссылку валидной → она уходит в inline-кнопку, и текст
        # заканчивается ровно на «**Текст заявки:**\n» (без превью и без markdown-ссылки).
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
            patch.object(notif, "_build_ticket_url", return_value="https://portal.example.com/x"),
        ):
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message(text="")
            )
        text = enqueue.await_args.kwargs["text"]
        assert "**Текст заявки:**" in text
        # ``body_preview`` пустой → ветка ``if body_preview`` пропущена →
        # список ``lines`` оканчивается ровно на лейбле (join без trailing \n).
        assert text.endswith("**Текст заявки:**")

    @pytest.mark.asyncio
    async def test_requester_label_falls_back_to_email_when_no_full_name(self):
        """Requester есть в системе, но без ``full_name`` → подпись берётся из
        ``requester.email`` (вторая ветка в каскаде ``requester_label``)."""
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1)
        requester = SimpleNamespace(full_name=None, email="known@company.local", attributes={})
        with (
            _patch_resolve_requester(requester),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        text = enqueue.await_args.kwargs["text"]
        assert "known@company.local" in text
        assert "**Заявка от known@company.local**" in text

    @pytest.mark.asyncio
    async def test_requester_label_falls_back_to_ticket_snapshot_when_no_contacts(self):
        """Requester есть, но без ``full_name`` И без ``email`` → берётся снимок
        из тикета (``requester_email``/``requester_name``)."""
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(
            number=1,
            requester_email="snapshot@external.com",
            requester_name="Снимок",
        )
        # Независимо от того, что requester.email — None, должна пройти ветка
        # ``ticket.requester_email or ticket.requester_name``.
        requester = SimpleNamespace(full_name=None, email=None, attributes={})
        with (
            _patch_resolve_requester(requester),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        text = enqueue.await_args.kwargs["text"]
        assert "snapshot@external.com" in text
        assert "**Заявка от snapshot@external.com**" in text

    @pytest.mark.asyncio
    async def test_requester_city_as_list_uses_first_element(self):
        """Keycloak иногда отдаёт multi-valued attributes как ``list[str]``.
        Первый элемент списка берётся как город."""
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1)
        requester = SimpleNamespace(
            full_name="Иван",
            email="x@y.z",
            attributes={"city": ["Архангельск", "Североморск"]},
        )
        with (
            _patch_resolve_requester(requester),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        text = enqueue.await_args.kwargs["text"]
        assert "**Город:** Архангельск" in text
        assert "Североморск" not in text

    @pytest.mark.asyncio
    async def test_requester_city_blank_string_falls_back_to_dash(self):
        """``city=""`` (или только пробелы) после ``.strip()`` — эквивалентно
        отсутствию города → прочерк."""
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1)
        requester = SimpleNamespace(
            full_name="Иван",
            email="x@y.z",
            attributes={"city": "   "},
        )
        with (
            _patch_resolve_requester(requester),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=_first_message())
        text = enqueue.await_args.kwargs["text"]
        assert "**Город:** —" in text

    # ── Регрессия бага 20.07.2026: подпись в превью MAX-уведомления ──────────

    # Сокращённый HTML подписи (маркер Mage_Ru.png, как в email_signature-тестах).
    _SIG_HTML = (
        "<p>Принтер сломался</p>"
        '<table><tr><td><img src="https://mage.ru/sign/Mage_Ru.png"></td>'
        "<td><b>Вячеслав Борзихин</b><br>+7 (8152) 400 580</td></tr></table>"
    )
    # ``body_text`` «грязный» — как будто подпись не отрезалась в ingress
    # (симулирует legacy-запись в БД до фикса _extract_bodies).
    _SIG_DIRTY_PLAIN = (
        "Принтер сломался\n\nВячеслав Борзихин\nРуководитель отдела ИТ\n+7 (8152) 400 580"
    )

    @pytest.mark.asyncio
    async def test_signature_excluded_from_preview_when_html_present(self):
        """Defence-in-depth: превью берётся из ``body_html`` (если есть) с
        повторной очисткой ``strip_email_signature``. Даже если ``body_text``
        содержит подпись (legacy-запись до фикса ingress), в MAX она не попадёт.

        Регрессия бага 20.07.2026: превью читалось напрямую из ``body_text``
        (plain), который для multipart/alternative писем содержал подпись.
        """
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=99, subject="Принтер")
        first_msg = _first_message(
            text=self._SIG_DIRTY_PLAIN,  # грязный plain (с подписью)
            html=self._SIG_HTML,  # html с подписью (будет почищен)
        )
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=first_msg)
        text = enqueue.await_args.kwargs["text"]
        # Тело заявки сохраняется в превью.
        assert "Принтер сломался" in text
        # Подпись НИКОГДА не попадает в MAX-уведомление.
        assert "Вячеслав Борзихин" not in text
        assert "Руководитель отдела ИТ" not in text
        assert "+7 (8152) 400 580" not in text

    @pytest.mark.asyncio
    async def test_preview_falls_back_to_body_text_when_no_html(self):
        """Контроль: если ``body_html`` отсутствует (web-сабмит без TipTap,
        legacy-запись), превью берётся из ``body_text`` как есть — без подписи
        для чистого plain (контроль обратной совместимости с 22 существующими
        тестами).
        """
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1, subject="Тема")
        first_msg = _first_message(text="Чистый текст заявки", html=None)
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(db, ticket=ticket, first_message=first_msg)
        text = enqueue.await_args.kwargs["text"]
        assert "Чистый текст заявки" in text


class TestIsMaxLinkSafeUrl:
    """``_is_max_link_safe_url`` — предикат «пройдёт ли URL валидацию MAX Bot API
    для inline-кнопки». Защита от 400 permanent ``Must have only http/https
    links format in buttons`` (см. WIP-план helpdesk-max-messenger от 20.07.2026).

    Эмпирическая карта (проверено запросами к живому MAX API 20.07.2026):

        ✅ https://example.com/x              (публичный TLD)
        ✅ https://portal.company.ru/x        (публичный TLD)
        ✅ https://10.0.0.5/x                 (private RFC1918 IP)
        ✅ https://172.16.0.1/x               (private RFC1918 IP)
        ✅ https://127.0.0.1/x                (loopback IP)
        ✅ https://[::1]/x                    (IPv6 loopback)
        ❌ https://portal.local/x             (special-use TLD — частый кейс интранета)
        ❌ http://localhost:8080/x            (hostname-only)
        ❌ https://portal.internal/x          (non-ICANN TLD)
        ❌ https://portal.lan/x               (non-ICANN TLD)
        ❌ https://portal.test/x              (RFC 6761 reserved)
        ❌ https://portal.home/x              (reserved)
        ❌ ftp://example.com/x                (не http/https)
    """

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/x",
            "https://portal.company.ru/x",
            "http://example.com:8080/path?q=1",
            "https://10.0.0.5/x",  # private RFC1918
            "https://172.16.0.1/x",
            "https://192.168.1.10/x",
            "https://127.0.0.1/x",  # loopback IP — MAX принимает
            "https://[::1]/x",  # IPv6 loopback
        ],
    )
    def test_safe_urls_pass(self, url):
        assert notif._is_max_link_safe_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://portal.local/x",  # типичный интранет-домен портала
            "http://localhost:8080/x",
            "https://portal.internal/x",
            "https://portal.lan/x",
            "https://portal.home/x",
            "https://portal.test/x",
            "https://portal.invalid/x",
            "https://portal.onion/x",
            "https://portal.arpa/x",
            "ftp://example.com/x",  # не http/https scheme
            "/helpdesk/tickets/abc",  # относительный путь (нет scheme)
            "not-a-url",
            "",
        ],
    )
    def test_unsafe_urls_rejected(self, url):
        assert notif._is_max_link_safe_url(url) is False
