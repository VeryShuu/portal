"""Characterization tests for the read-only Helpdesk archive view."""

# mypy: disable-error-code="arg-type,attr-defined"

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.helpdesk import media, tickets
from app.api.helpdesk._common import archived_ticket_to_agent_out, archived_ticket_to_list_out
from app.models.helpdesk import HelpdeskTicketArchive
from app.services.helpdesk import archive
from app.services.helpdesk.archive import _as_archived_ticket


def _archive_row() -> HelpdeskTicketArchive:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    return HelpdeskTicketArchive(
        id=uuid4(),
        number=42,
        subject="Archived ticket",
        requester_email="requester@example.test",
        requester_user_id=uuid4(),
        assignee_user_id=uuid4(),
        opened_at=now,
        closed_at=now,
        closed_by_user_id=uuid4(),
        payload={
            "ticket": {
                "description": "Original request",
                "description_html": "<p>Original request</p>",
                "source": "web",
                "requester_name": "Requester",
            },
            "messages": [
                {
                    "id": str(uuid4()),
                    "direction": "inbound",
                    "author_email": "requester@example.test",
                    "body_text": "Historic reply",
                    "body_html": "<p>Historic reply</p>",
                    "created_at": now.isoformat(),
                }
            ],
        },
    )


def test_archived_ticket_maps_to_read_only_list_item() -> None:
    ticket = _as_archived_ticket(_archive_row())

    result = archived_ticket_to_list_out(ticket, assignee_name="Agent")

    assert result.archived is True
    assert result.status == "closed"
    assert result.assignee_name == "Agent"


def test_archived_ticket_maps_legacy_snapshot_messages_without_fake_attachments() -> None:
    ticket = _as_archived_ticket(_archive_row())

    result = archived_ticket_to_agent_out(ticket, assignee_name="Agent")

    assert result.archived is True
    assert result.messages[0].body_text == "Historic reply"
    assert result.messages[0].attachments == []
    assert result.participants[0].is_requester is True


def test_archived_ticket_exposes_preserved_legacy_attachment_via_archive_url() -> None:
    row = _archive_row()
    row.payload["attachments_meta"] = [
        {
            "filename": "stored.pdf",
            "original_name": "history.pdf",
            "content_type": "application/pdf",
            "size_bytes": 123,
            "created_at": row.closed_at.isoformat(),
        }
    ]

    result = archived_ticket_to_agent_out(_as_archived_ticket(row))

    attachment = result.messages[0].attachments[0]
    assert attachment.original_name == "history.pdf"
    assert (
        attachment.download_url
        == f"/api/v1/helpdesk/tickets/{row.id}/archive-attachments/stored.pdf"
    )


def test_archived_ticket_maps_enriched_message_and_invalid_legacy_values() -> None:
    row = _archive_row()
    message_id = uuid4()
    author_id = uuid4()
    row.payload["ticket"]["last_activity_at"] = "not-a-date"
    row.payload["messages"] = [
        {"id": "bad", "direction": "inbound"},
        {"id": str(message_id), "direction": "unknown"},
        {
            "id": str(message_id),
            "direction": "outbound",
            "source": "web",
            "author_email": "agent@example.test",
            "author_name": "Agent",
            "author_user_id": str(author_id),
            "body_text": "Answer",
            "body_html": "<p>Answer</p>",
            "cc": [{"email": "copy@example.test", "name": "Copy"}],
            "created_at": datetime(2026, 8, 12).isoformat(),
            "attachments": [
                {
                    "id": str(uuid4()),
                    "filename": "answer.pdf",
                    "original_name": "answer.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 11,
                }
            ],
        },
    ]

    result = archived_ticket_to_agent_out(_as_archived_ticket(row))

    assert result.last_activity_at == row.closed_at
    assert len(result.messages) == 1
    assert result.messages[0].author_user_id == author_id
    assert result.messages[0].cc[0].email == "copy@example.test"
    assert result.messages[0].attachments[0].filename == "answer.pdf"


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalars(self) -> "_ScalarResult":
        return self

    def all(self) -> object:
        return self._value

    def one_or_none(self) -> object:
        return self._value


async def test_archive_service_filters_and_fetches_read_models() -> None:
    row = _archive_row()
    db = SimpleNamespace(execute=AsyncMock(side_effect=[_ScalarResult([row]), _ScalarResult(row)]))

    listed = await archive.list_archived_tickets(
        db, requester_user_id=row.requester_user_id, source="web", query="historic"
    )
    fetched = await archive.fetch_archived_ticket(db, ticket_id=row.id)

    assert [item.id for item in listed] == [row.id]
    assert fetched is not None and fetched.id == row.id


async def test_archive_service_resolves_requester_or_returns_none() -> None:
    ticket = _as_archived_ticket(_archive_row())
    user = SimpleNamespace(id=ticket.row.requester_user_id)
    db = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult(user)))

    assert await archive.resolve_archived_requester_user(db, ticket=ticket) is user
    ticket.row.requester_user_id = None
    assert await archive.resolve_archived_requester_user(db, ticket=ticket) is None


async def test_archive_file_cleanup_is_explicit_noop() -> None:
    assert await archive.cleanup_archived_files(SimpleNamespace()) == 0


async def test_closed_lists_merge_archive_before_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archived = _as_archived_ticket(_archive_row())
    user = SimpleNamespace(id=archived.row.requester_user_id)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    monkeypatch.setattr(tickets.tickets_service, "list_my_tickets", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        tickets.archive_service, "list_archived_tickets", AsyncMock(return_value=[archived])
    )

    result = await tickets.list_my_tickets(
        user=user,
        db=db,
        status_filter="closed",
        unassigned=False,
        assigned=False,
        active_only=False,
        sort=None,
        order="desc",
        limit=1,
        offset=0,
    )

    assert result.total == 1
    assert result.items[0].archived is True


async def test_archive_assignee_names_skips_query_when_nobody_is_assigned() -> None:
    row = _archive_row()
    row.assignee_user_id = None
    db = SimpleNamespace(execute=AsyncMock())

    assert await tickets._archive_assignee_names(db, [_as_archived_ticket(row)]) == {}
    db.execute.assert_not_awaited()


async def test_closed_agent_list_and_detail_read_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    archived = _as_archived_ticket(_archive_row())
    agent = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    monkeypatch.setattr(tickets.tickets_service, "list_agent_tickets", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        tickets.archive_service, "list_archived_tickets", AsyncMock(return_value=[archived])
    )
    monkeypatch.setattr(
        tickets.tickets_service, "fetch_ticket_for_agent", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        tickets.archive_service, "fetch_archived_ticket", AsyncMock(return_value=archived)
    )
    monkeypatch.setattr(
        tickets.archive_service, "resolve_archived_requester_user", AsyncMock(return_value=None)
    )

    listed = await tickets.list_all_tickets(
        agent=agent,
        db=db,
        status_filter="closed",
        assignee=None,
        unassigned=False,
        source=None,
        active_only=False,
        assigned=False,
        q=None,
        sort=None,
        order="desc",
        limit=1,
        offset=0,
    )
    detail = await tickets.get_ticket(ticket_id=archived.id, agent=agent, db=db)

    assert listed.items[0].archived is True
    assert detail.archived is True


async def test_media_serving_falls_back_to_authorized_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archived = _as_archived_ticket(_archive_row())
    user = SimpleNamespace(id=archived.row.requester_user_id)
    monkeypatch.setattr(
        media, "_fetch_ticket_for_media", AsyncMock(side_effect=media.HTTPException(404))
    )
    monkeypatch.setattr(
        media.archive_service, "fetch_archived_ticket", AsyncMock(return_value=archived)
    )

    assert (
        await media._fetch_ticket_number_for_serving(
            SimpleNamespace(), ticket_id=archived.id, user=user, is_agent=False
        )
        == archived.row.number
    )


async def test_media_archive_fallback_hides_foreign_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    archived = _as_archived_ticket(_archive_row())
    monkeypatch.setattr(
        media, "_fetch_ticket_for_media", AsyncMock(side_effect=media.HTTPException(404))
    )
    monkeypatch.setattr(
        media.archive_service, "fetch_archived_ticket", AsyncMock(return_value=archived)
    )

    with pytest.raises(media.HTTPException) as exc_info:
        await media._fetch_ticket_number_for_serving(
            SimpleNamespace(),
            ticket_id=archived.id,
            user=SimpleNamespace(id=uuid4()),
            is_agent=False,
        )
    assert exc_info.value.status_code == 404
