"""Integration tests for the object-directories API on a real PostgreSQL.

Route functions are invoked directly (same style as ``test_photos_api.py``) on a
SAVEPOINT-isolated session. The master ``directories`` module flag is supplied
by patching ``app.api.directories.load_modules_shared``; Redis is mocked (audit
only does ``rpush``).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.core.modules_config import AllModuleSettings, DirectoriesModuleSettings
from app.schemas.object_directory import (
    ContactInput,
    CreateDirectoryRequest,
    CreateEntryRequest,
    DirectoryChannel,
    DirectoryField,
    EntryReorderItem,
    ReorderEntriesRequest,
    UpdateEntryRequest,
)

pytestmark = pytest.mark.asyncio


def _modules(enabled: bool = True) -> AllModuleSettings:
    return AllModuleSettings(directories=DirectoriesModuleSettings(enabled=enabled))


def _enabled_patch(enabled: bool = True):
    return patch(
        "app.api.directories.load_modules_shared",
        new_callable=AsyncMock,
        return_value=_modules(enabled),
    )


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.rpush = AsyncMock()
    return r


def _field(key: str, required: bool = False) -> DirectoryField:
    return DirectoryField(key=key, label_ru=key.upper(), required=required)


def _create_req(slug: str) -> CreateDirectoryRequest:
    return CreateDirectoryRequest(
        slug=slug,
        label_ru="Флот",
        label_en="Fleet",
        field_schema=[_field("imo", required=True), _field("mmsi")],
        channels=[DirectoryChannel(key="email", label_ru="E-mail")],
    )


@pytest_asyncio.fixture
async def directory(real_db_session, real_editor):
    from app.api.directories import create_directory

    slug = f"fleet{uuid.uuid4().hex[:6]}"
    with _enabled_patch():
        return await create_directory(_create_req(slug), real_editor, real_db_session, _redis())


class TestDirectoryTypes:
    async def test_create_and_list(self, real_db_session, real_editor, real_user, directory):
        from app.api.directories import list_directories

        assert directory.slug.startswith("fleet")
        with _enabled_patch():
            listed = await list_directories(real_user, real_db_session, _redis())
        assert any(d.id == directory.id for d in listed.items)

    async def test_module_off_returns_404(self, real_db_session, real_user):
        from app.api.directories import list_directories

        with _enabled_patch(enabled=False), pytest.raises(HTTPException) as exc:
            await list_directories(real_user, real_db_session, _redis())
        assert exc.value.status_code == 404

    async def test_create_emits_audit(self, real_db_session, real_editor):
        from app.api.directories import create_directory

        slug = f"wh{uuid.uuid4().hex[:6]}"
        with (
            _enabled_patch(),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock) as audit,
        ):
            await create_directory(_create_req(slug), real_editor, real_db_session, _redis())
        assert audit.await_count == 1
        assert audit.await_args.kwargs["event_type"] == "directories.type_created"


class TestEntries:
    async def test_create_list_pagination(self, real_db_session, real_editor, real_user, directory):
        from app.api.directories import create_entry, list_entries

        with _enabled_patch():
            for i in range(3):
                await create_entry(
                    directory.slug,
                    CreateEntryRequest(name=f"Ship {i}", attributes={"imo": f"100{i}"}),
                    real_editor,
                    real_db_session,
                    _redis(),
                )
            page = await list_entries(
                directory.slug, real_user, real_db_session, _redis(), q=None, limit=2, offset=0
            )
        assert page.total == 3
        assert page.limit == 2
        assert page.offset == 0
        assert len(page.items) == 2

    async def test_invalid_attribute_rejected(self, real_db_session, real_editor, directory):
        from app.api.directories import create_entry

        with _enabled_patch(), pytest.raises(HTTPException) as exc:
            await create_entry(
                directory.slug,
                CreateEntryRequest(name="X", attributes={"bogus": "1", "imo": "1"}),
                real_editor,
                real_db_session,
                _redis(),
            )
        assert exc.value.status_code == 422

    async def test_search_by_name(self, real_db_session, real_editor, directory):
        from app.api.directories import create_entry
        from app.services.search.entities import search_directory_entries

        unique = f"Kazanin{uuid.uuid4().hex[:6]}"
        with _enabled_patch():
            await create_entry(
                directory.slug,
                CreateEntryRequest(name=unique, attributes={"imo": "9489481"}),
                real_editor,
                real_db_session,
                _redis(),
            )
        total, items = await search_directory_entries(
            real_db_session, q=unique, limit=10, offset=0
        )
        assert total == 1
        assert items[0].title == unique
        assert items[0].url == f"/staff?tab={directory.slug}"

    async def test_update_and_soft_delete(self, real_db_session, real_editor, real_user, directory):
        from app.api.directories import create_entry, delete_entry, list_entries

        with _enabled_patch():
            entry = await create_entry(
                directory.slug,
                CreateEntryRequest(
                    name="Old",
                    attributes={"imo": "1"},
                    contacts=[ContactInput(channel="email", value="a@b.ru")],
                ),
                real_editor,
                real_db_session,
                _redis(),
            )
            assert len(entry.contacts) == 1

            from app.api.directories import update_entry

            updated = await update_entry(
                directory.slug,
                entry.id,
                UpdateEntryRequest(name="New"),
                real_editor,
                real_db_session,
                _redis(),
            )
            assert updated.name == "New"

            await delete_entry(directory.slug, entry.id, real_editor, real_db_session, _redis())
            page = await list_entries(
                directory.slug, real_user, real_db_session, _redis(), q=None, limit=50, offset=0
            )
        assert all(e.id != entry.id for e in page.items)

    async def test_reorder_entries(self, real_db_session, real_editor, real_user, directory):
        from app.api.directories import create_entry, list_entries, reorder_entries

        with _enabled_patch():
            created = [
                await create_entry(
                    directory.slug,
                    CreateEntryRequest(name=f"Ship {i}", attributes={"imo": f"200{i}"}),
                    real_editor,
                    real_db_session,
                    _redis(),
                )
                for i in range(3)
            ]
            reversed_ids = [e.id for e in reversed(created)]
            await reorder_entries(
                directory.slug,
                ReorderEntriesRequest(
                    items=[
                        EntryReorderItem(id=eid, sort_order=idx)
                        for idx, eid in enumerate(reversed_ids)
                    ]
                ),
                real_editor,
                real_db_session,
                _redis(),
            )
            page = await list_entries(
                directory.slug, real_user, real_db_session, _redis(), q=None, limit=50, offset=0
            )
        assert [e.id for e in page.items] == reversed_ids

    async def test_reorder_unknown_entry_404(self, real_db_session, real_editor, directory):
        from app.api.directories import reorder_entries

        with _enabled_patch(), pytest.raises(HTTPException) as exc:
            await reorder_entries(
                directory.slug,
                ReorderEntriesRequest(
                    items=[EntryReorderItem(id=uuid.uuid4(), sort_order=0)]
                ),
                real_editor,
                real_db_session,
                _redis(),
            )
        assert exc.value.status_code == 404


class TestPerTypeGating:
    async def test_disabled_type_hidden_for_reader(self, real_db_session, real_editor, real_user):
        from app.api.directories import create_directory, list_entries

        slug = f"hidden{uuid.uuid4().hex[:6]}"
        req = _create_req(slug)
        req.enabled = False
        with _enabled_patch():
            await create_directory(req, real_editor, real_db_session, _redis())
            with pytest.raises(HTTPException) as exc:
                await list_entries(
                    slug, real_user, real_db_session, _redis(), q=None, limit=10, offset=0
                )
            assert exc.value.status_code == 404
            # editor can still see it
            page = await list_entries(
                slug, real_editor, real_db_session, _redis(), q=None, limit=10, offset=0
            )
        assert page.total == 0


class TestRbac:
    async def test_reader_rejected_by_editor_dep(self, real_user):
        from app.api.deps import require_role

        check = require_role("editor", "admin")
        with pytest.raises(HTTPException) as exc:
            await check(real_user)
        assert exc.value.status_code == 403

