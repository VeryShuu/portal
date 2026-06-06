"""Unit-тесты для app/api/files/_share_drift.py::move_file_shares.

Покрытие F6: при перемещении/переименовании файла переносятся ВСЕ шары
(активные и отозванные), чтобы на старом пути не оставалась «осиротевшая»
история отзывов, которую унаследует новый файл с тем же именем.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed locally")


def _make_share(*, revoked: bool) -> SimpleNamespace:
    return SimpleNamespace(
        folder_id=uuid.uuid4(),
        filename="old.txt",
        nc_path="PortalFiles/src/old.txt",
        revoked_at=datetime.now(UTC) if revoked else None,
        subject_type="user",
        subject_id=uuid.uuid4(),
        subject_name="User",
        permission="viewer",
        expires_at=None,
    )


def _make_db(shares: list) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = shares
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
async def test_move_repoints_active_and_revoked_shares():
    from app.api.files import _share_drift

    active = _make_share(revoked=False)
    revoked = _make_share(revoked=True)
    db = _make_db([active, revoked])
    redis = AsyncMock()

    dst_folder = uuid.uuid4()
    src_folder = active.folder_id

    with (
        patch.object(_share_drift, "_persist_active", new=AsyncMock()),
        patch.object(_share_drift, "drop_file_shares", new=AsyncMock()),
        patch.object(_share_drift, "invalidate_file_share_cache", new=AsyncMock()),
    ):
        await _share_drift.move_file_shares(
            db,
            redis,
            src_folder_id=src_folder,
            src_filename="old.txt",
            src_nc_path="PortalFiles/src/old.txt",
            dst_folder_id=dst_folder,
            dst_filename="new.txt",
            dst_nc_path="PortalFiles/dst/new.txt",
        )

    for s in (active, revoked):
        assert s.folder_id == dst_folder
        assert s.filename == "new.txt"
        assert s.nc_path == "PortalFiles/dst/new.txt"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_move_noop_when_no_shares():
    from app.api.files import _share_drift

    db = _make_db([])
    redis = AsyncMock()

    with (
        patch.object(_share_drift, "_persist_active", new=AsyncMock()) as persist,
        patch.object(_share_drift, "drop_file_shares", new=AsyncMock()) as drop,
    ):
        await _share_drift.move_file_shares(
            db,
            redis,
            src_folder_id=uuid.uuid4(),
            src_filename="old.txt",
            src_nc_path="PortalFiles/src/old.txt",
            dst_folder_id=uuid.uuid4(),
            dst_filename="new.txt",
            dst_nc_path="PortalFiles/dst/new.txt",
        )

    db.commit.assert_not_awaited()
    persist.assert_not_awaited()
    drop.assert_not_awaited()
