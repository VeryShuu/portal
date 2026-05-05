"""Unit tests for photos share-token resolution logic (TTL + revoke).

Covers:
- _resolve_token: revoked token → 404
- _resolve_token: expired token (expires_at in past) → 410
- _resolve_token: valid token → returns (photo, folder)
- _resolve_folder_token_sync_check: revoked token → 410
- _resolve_folder_token_sync_check: expired token → 410
- _resolve_folder_token_sync_check: valid token → no exception
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _make_token(
    *,
    revoked_at: datetime | None = None,
    expires_at: datetime | None = None,
    photo_id: uuid.UUID | None = None,
) -> MagicMock:
    tok = MagicMock()
    tok.revoked_at = revoked_at
    tok.expires_at = expires_at
    tok.photo_id = photo_id or uuid.uuid4()
    return tok


def _make_folder_token(
    *,
    revoked_at: datetime | None = None,
    expires_at: datetime | None = None,
    folder_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        revoked_at=revoked_at,
        expires_at=expires_at,
        folder_id=folder_id or uuid.uuid4(),
    )


class TestResolveFolderTokenSyncCheck:
    def _call(self, token_row):
        from app.api.photos.sharing import _resolve_folder_token_sync_check

        _resolve_folder_token_sync_check(token_row)

    def test_valid_token_no_exception(self):
        tok = _make_folder_token(expires_at=datetime.now(UTC) + timedelta(days=7))
        self._call(tok)

    def test_no_expiry_no_exception(self):
        tok = _make_folder_token(expires_at=None, revoked_at=None)
        self._call(tok)

    def test_revoked_token_raises_410(self):
        tok = _make_folder_token(revoked_at=datetime.now(UTC))
        with pytest.raises(HTTPException) as exc_info:
            self._call(tok)
        assert exc_info.value.status_code == 410

    def test_expired_token_raises_410(self):
        tok = _make_folder_token(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        with pytest.raises(HTTPException) as exc_info:
            self._call(tok)
        assert exc_info.value.status_code == 410

    def test_just_expired_token_raises_410(self):
        tok = _make_folder_token(expires_at=datetime.now(UTC) - timedelta(days=1))
        with pytest.raises(HTTPException) as exc_info:
            self._call(tok)
        assert exc_info.value.status_code == 410


class TestResolveToken:
    @pytest.mark.asyncio
    async def test_revoked_token_raises_404(self):
        from app.api.photos.sharing import _resolve_token

        token_str = "valid-token-string"
        tok = _make_token(revoked_at=datetime.now(UTC))

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tok
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_token(db, token_str)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_token_raises_404(self):
        from app.api.photos.sharing import _resolve_token

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_token(db, "no-such-token")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_expired_token_raises_410(self):
        from app.api.photos.sharing import _resolve_token

        photo_id = uuid.uuid4()
        tok = _make_token(
            expires_at=datetime.now(UTC) - timedelta(hours=1),
            photo_id=photo_id,
        )

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tok
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_token(db, "expired-token")
        assert exc_info.value.status_code == 410

    @pytest.mark.asyncio
    async def test_valid_token_returns_photo_and_folder(self):
        from app.api.photos.sharing import _resolve_token

        photo_id = uuid.uuid4()
        folder_id = uuid.uuid4()

        tok = _make_token(
            expires_at=datetime.now(UTC) + timedelta(days=7),
            photo_id=photo_id,
        )
        photo = MagicMock()
        photo.id = photo_id
        photo.folder_id = folder_id
        folder = MagicMock()
        folder.id = folder_id

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            res = MagicMock()
            if call_count == 0:
                res.scalar_one_or_none.return_value = tok
            elif call_count == 1:
                res.scalar_one_or_none.return_value = photo
            call_count += 1
            return res

        db = AsyncMock()
        db.execute = _execute
        db.scalar = AsyncMock(return_value=folder)

        result_photo, result_folder = await _resolve_token(db, "good-token")
        assert result_photo is photo
        assert result_folder is folder

    @pytest.mark.asyncio
    async def test_no_expiry_valid_token_returns_photo_and_folder(self):
        from app.api.photos.sharing import _resolve_token

        photo_id = uuid.uuid4()
        folder_id = uuid.uuid4()

        tok = _make_token(expires_at=None, photo_id=photo_id)
        photo = MagicMock()
        photo.id = photo_id
        photo.folder_id = folder_id
        folder = MagicMock()
        folder.id = folder_id

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            res = MagicMock()
            if call_count == 0:
                res.scalar_one_or_none.return_value = tok
            elif call_count == 1:
                res.scalar_one_or_none.return_value = photo
            call_count += 1
            return res

        db = AsyncMock()
        db.execute = _execute
        db.scalar = AsyncMock(return_value=folder)

        result_photo, result_folder = await _resolve_token(db, "good-token-no-expiry")
        assert result_photo is photo
        assert result_folder is folder
