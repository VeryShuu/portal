"""Unit-тесты ORM-моделей helpdesk (Этап 1 — БД + модели + схемы).

Проверяют метаданные таблиц без обращения к БД: соответствие ТЗ
``docs/wip/helpdesk.md`` §3 по именам таблиц, колонок, типов, IDENTITY-колонки
``number``, частичных/уникальных индексов и ondelete-политик FK.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.helpdesk import (
    HelpdeskAgent,
    HelpdeskAttachment,
    HelpdeskEmailLog,
    HelpdeskMailboxSettings,
    HelpdeskMessage,
    HelpdeskTicket,
    HelpdeskTicketArchive,
)


def _columns(table: sa.Table) -> dict[str, sa.Column]:
    return {c.name: c for c in table.columns}


class TestHelpdeskTicket:
    def test_table_name(self) -> None:
        assert HelpdeskTicket.__tablename__ == "helpdesk_tickets"

    def test_number_is_identity_always(self) -> None:
        col = HelpdeskTicket.__table__.c.number
        # Identity(always=True) → GENERATED ALWAYS AS IDENTITY (ТЗ §3.1).
        identity = col.identity
        assert identity is not None
        assert identity.always is True

    def test_key_columns_and_types(self) -> None:
        cols = _columns(HelpdeskTicket.__table__)
        assert isinstance(cols["id"].type, UUID)
        assert isinstance(cols["number"].type, sa.BigInteger)
        assert isinstance(cols["subject"].type, sa.String)
        assert cols["subject"].type.length == 500
        assert isinstance(cols["description"].type, sa.Text)
        assert cols["status"].type.length == 20
        assert cols["source"].type.length == 20
        assert cols["requester_email"].type.length == 320
        assert isinstance(cols["references_archived_ticket_number"].type, sa.BigInteger)

    def test_no_fk_on_references_archived(self) -> None:
        # Архивная таблица партиционная — FK на неё невозможен (ТЗ §3.1).
        col = HelpdeskTicket.__table__.c.references_archived_ticket_number
        assert len(col.foreign_keys) == 0

    def test_user_fks_set_null_on_delete(self) -> None:
        cols = _columns(HelpdeskTicket.__table__)
        for name in ("requester_user_id", "assignee_user_id", "closed_by_user_id"):
            fks = list(cols[name].foreign_keys)
            assert len(fks) == 1, name
            assert fks[0].ondelete == "SET NULL", name

    def test_indexes(self) -> None:
        names = {i.name for i in HelpdeskTicket.__table__.indexes}
        assert {
            "ix_helpdesk_tickets_status",
            "ix_helpdesk_tickets_assignee",
            "ix_helpdesk_tickets_requester",
            "ix_helpdesk_tickets_email",
            "ix_helpdesk_tickets_last_activity",
            "ix_helpdesk_tickets_open_list",
            "ix_helpdesk_tickets_ref_archive",
        } <= names

    def test_ticket_number_property(self) -> None:
        t = HelpdeskTicket(
            subject="x",
            description="y",
            source="web",
            requester_email="a@b.c",
            number=42,
        )
        assert t.ticket_number == "TKT-42"


class TestHelpdeskMessage:
    def test_table_name(self) -> None:
        assert HelpdeskMessage.__tablename__ == "helpdesk_messages"

    def test_ticket_fk_cascade(self) -> None:
        fk = next(iter(HelpdeskMessage.__table__.c.ticket_id.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_email_message_id_unique_partial(self) -> None:
        # Частичный уникальный индекс (WHERE email_message_id IS NOT NULL).
        idx = next(
            i
            for i in HelpdeskMessage.__table__.indexes
            if i.name == "uq_helpdesk_messages_email_msg_id"
        )
        assert idx.unique is True

    def test_direction_visibility_length(self) -> None:
        cols = _columns(HelpdeskMessage.__table__)
        assert cols["direction"].type.length == 10
        assert cols["visibility"].type.length == 10


class TestHelpdeskAttachment:
    def test_filename_and_original_name_present(self) -> None:
        # Этап 4: хранение локальное, storage_backend/storage_key удалены.
        # Имя на диссе + оригинальное имя (как в FeedbackAttachment).
        cols = _columns(HelpdeskAttachment.__table__)
        assert "storage_backend" not in cols
        assert "storage_key" not in cols
        assert cols["filename"].type.length == 500
        assert cols["original_name"].type.length == 500
        assert not cols["filename"].nullable
        assert not cols["original_name"].nullable

    def test_size_bytes_bigint(self) -> None:
        assert isinstance(HelpdeskAttachment.__table__.c.size_bytes.type, sa.BigInteger)

    def test_ticket_fk_cascade(self) -> None:
        fk = next(iter(HelpdeskAttachment.__table__.c.ticket_id.foreign_keys))
        assert fk.ondelete == "CASCADE"


class TestHelpdeskAgent:
    def test_user_id_is_primary_key(self) -> None:
        col = HelpdeskAgent.__table__.c.user_id
        assert col.primary_key
        assert next(iter(col.foreign_keys)).ondelete == "CASCADE"

    def test_notify_new_server_default_true(self) -> None:
        # Python-side default срабатывает при INSERT, не при конструировании;
        # проверяем server_default из метаданных (DB DEFAULT TRUE — ТЗ §3.4).
        col = HelpdeskAgent.__table__.c.notify_new
        assert col.server_default is not None


class TestHelpdeskEmailLog:
    def test_message_id_is_primary_key(self) -> None:
        col = HelpdeskEmailLog.__table__.c.message_id
        assert col.primary_key
        assert isinstance(col.type, sa.String)
        assert col.type.length == 998


class TestHelpdeskMailboxSettings:
    def test_singleton_default(self) -> None:
        col = HelpdeskMailboxSettings.__table__.c.id
        assert col.primary_key

    def test_password_enc_text_not_nullable(self) -> None:
        col = HelpdeskMailboxSettings.__table__.c.imap_password_enc
        assert isinstance(col.type, sa.Text)
        assert not col.nullable


class TestHelpdeskTicketArchive:
    def test_payload_jsonb(self) -> None:
        assert isinstance(HelpdeskTicketArchive.__table__.c.payload.type, JSONB)

    def test_composite_pk(self) -> None:
        table = HelpdeskTicketArchive.__table__
        pk_cols = {c.name for c in table.primary_key.columns}
        assert pk_cols == {"id", "closed_at"}
