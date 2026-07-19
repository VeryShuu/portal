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
    *, uid: uuid.UUID | None = None, email: str = "agent@company.local"
) -> SimpleNamespace:
    """Агент как User-заглушка (нужен только id+email для enqueue)."""
    return SimpleNamespace(id=uid or uuid.uuid4(), email=email, full_name="Агент")


def _first_message(*, text: str = "Текст заявки", html: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(body_text=text, body_html=html)


def _requester_user(
    *,
    full_name: str = "Иван Петров",
    email: str = "ivan@company.local",
    phone: str | None = "12-34",
    mobile: str | None = "+7 999 111-22-33",
) -> SimpleNamespace:
    """Модель User-заявителя (контакты берутся из неё, как в карточке тикета)."""
    attrs = {"mobile": mobile} if mobile else {}
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
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message()
            )
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
        ):
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message(text="Подключиться не могу")
            )
        text = enqueue.await_args.kwargs["text"]
        assert "#TKT-88" in text
        assert "Не работает VPN" in text
        # Превью первого сообщения тоже попадает в текст.
        assert "Подключиться не могу" in text

    @pytest.mark.asyncio
    async def test_text_contains_requester_label(self):
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=1, source="email")
        with (
            _patch_resolve_requester(_requester_user(full_name="Пётр Сидоров")),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message()
            )
        text = enqueue.await_args.kwargs["text"]
        assert "Пётр Сидоров" in text
        assert "email" in text  # source label

    @pytest.mark.asyncio
    async def test_payload_has_inline_keyboard_with_portal_url(self):
        """Payload включает attachments с inline_keyboard — кнопка-ссылка «Открыть
        на портале» ведёт на карточку тикета.

        Формат MAX (см. ``max-bot-api-client-ts/src/.../attachment.ts``):
        ``payload.buttons`` (НЕ ``rows``) — массив строк, каждая строка — массив
        кнопок. Кнопка-ссылка: ``{"type": "link", "text", "url"}``.
        """
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=99)
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message()
            )
        payload = enqueue.await_args.kwargs["payload"]
        assert "attachments" in payload
        kb = payload["attachments"][0]
        assert kb["type"] == "inline_keyboard"
        # Ключевое поле MAX — ``buttons``, не ``rows``.
        assert "buttons" in kb["payload"]
        assert "rows" not in kb["payload"]
        button = kb["payload"]["buttons"][0][0]
        assert button["type"] == "link"
        assert button["text"] == "Открыть на портале"
        assert "/helpdesk/tickets/" in button["url"]
        assert str(ticket.id) in button["url"]

    @pytest.mark.asyncio
    async def test_related_resource_is_ticket(self):
        db = _db_with_max_settings(_max_settings())
        ticket = _ticket(number=42)
        with (
            _patch_resolve_requester(_requester_user()),
            patch.object(notif, "enqueue_messenger_message", new=AsyncMock()) as enqueue,
        ):
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message()
            )
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
            await notif.notify_ticket_created_max(
                db, ticket=ticket, first_message=_first_message()
            )
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
        # Превью не длиннее 501 символа (500 + многоточие).
        preview_line = text.split("\n")[-1]
        assert len(preview_line) <= 501
        assert preview_line.endswith("…")
