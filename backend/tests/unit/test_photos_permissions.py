from __future__ import annotations

import uuid
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.api.photos.permissions import grant_folder_permission
from app.schemas.photos import GrantPermissionRequest


def _make_user(role: str = "admin") -> SimpleNamespace:
    uid = uuid.uuid4()
    return SimpleNamespace(
        id=uid,
        role=role,
        email="admin@test.local",
        keycloak_id=str(uid),
        keycloak_groups=[],
    )


def _make_folder(folder_id: uuid.UUID | None = None) -> SimpleNamespace:
    fid = folder_id or uuid.uuid4()
    return SimpleNamespace(
        id=fid,
        parent_id=None,
        created_by=uuid.uuid4(),
        deleted_at=None,
    )


def _make_perm(folder_id: uuid.UUID, subject_id: str) -> SimpleNamespace:
    from datetime import datetime, timezone

    return SimpleNamespace(
        id=uuid.uuid4(),
        folder_id=folder_id,
        subject_type="user",
        subject_id=subject_id,
        subject_name="Test User",
        permission="viewer",
        granted_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
    )


class TestGrantFolderPermissionIntegrityError:
    """12.3.4 — IntegrityError recovery in set_folder_permission."""

    @pytest.mark.asyncio
    async def test_integrity_error_then_existing_perm_updates(self) -> None:
        folder_id = uuid.uuid4()
        subject_id = str(uuid.uuid4())
        folder = _make_folder(folder_id)
        existing_perm = _make_perm(folder_id, subject_id)

        data = GrantPermissionRequest(
            subject_type="user",
            subject_id=subject_id,
            subject_name="Test User",
            permission="uploader",
        )
        user = _make_user()
        redis = AsyncMock()
        redis.scan_iter = MagicMock(return_value=_aiter([]))

        call_count = 0

        async def fake_execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = folder
            elif call_count == 2:
                result.scalar_one_or_none.return_value = None
            elif call_count == 3:
                result.scalar_one_or_none.return_value = existing_perm
            else:
                result.scalar_one_or_none.return_value = existing_perm
            return result

        db = AsyncMock()
        db.execute = fake_execute
        db.add = MagicMock()
        db.commit = AsyncMock(side_effect=[IntegrityError("dup", {}, Exception()), None])
        db.rollback = AsyncMock()
        db.refresh = AsyncMock()

        request = MagicMock()

        with (
            patch("app.api.photos.permissions.require_folder_permission", AsyncMock()),
            patch("app.api.photos.permissions.invalidate_folder_cache", AsyncMock()),
            patch("app.api.photos.permissions.push_audit_event", AsyncMock()),
        ):
            result = await grant_folder_permission(
                folder_id=folder_id,
                data=data,
                request=request,
                db=db,
                user=user,
                redis=redis,
            )

        assert result is not None
        assert existing_perm.permission == "uploader"
        db.rollback.assert_called_once()
        assert db.commit.call_count == 2

    @pytest.mark.asyncio
    async def test_integrity_error_no_existing_perm_raises_409(self) -> None:
        folder_id = uuid.uuid4()
        subject_id = str(uuid.uuid4())
        folder = _make_folder(folder_id)

        data = GrantPermissionRequest(
            subject_type="user",
            subject_id=subject_id,
            subject_name="Orphan User",
            permission="viewer",
        )
        user = _make_user()
        redis = AsyncMock()

        call_count = 0

        async def fake_execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = folder
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db = AsyncMock()
        db.execute = fake_execute
        db.add = MagicMock()
        db.commit = AsyncMock(side_effect=IntegrityError("dup", {}, Exception()))
        db.rollback = AsyncMock()

        request = MagicMock()

        with (
            patch("app.api.photos.permissions.require_folder_permission", AsyncMock()),
            patch("app.api.photos.permissions.invalidate_folder_cache", AsyncMock()),
            patch("app.api.photos.permissions.push_audit_event", AsyncMock()),
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await grant_folder_permission(
                    folder_id=folder_id,
                    data=data,
                    request=request,
                    db=db,
                    user=user,
                    redis=redis,
                )

        assert exc_info.value.status_code == 409
        db.rollback.assert_called_once()


async def _aiter(items):
    for i in items:
        yield i
