"""Unit-тесты сервиса аватарок справочников (``app.services.directory_avatar``).

Покрытие:
- ext-маппинг content-type → расширение (png/jpeg/webp), fallback на png;
- удаление прежнего файла при загрузке нового (``remove_avatar_files``);
- подмена URL на ``.webp`` при успешной оптимизации Pillow;
- проброс ``allowed_mimes``/``max_size`` в streaming-загрузчик.

Файловая система и Pillow замоканы: тесты не пишут в ``/data``.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile

from app.services import directory_avatar as avatar


def _upload(content_type: str = "image/png") -> UploadFile:
    return UploadFile(
        filename="x",
        file=io.BytesIO(b"bytes"),
        headers={"content-type": content_type},
    )


@pytest.mark.asyncio
class TestSaveAvatar:
    async def test_png_without_optimize_returns_png_url(self, tmp_path: Path):
        entry_id = uuid.uuid4()
        with (
            patch.object(avatar, "DIRECTORY_AVATARS_DIR", tmp_path),
            patch.object(avatar, "stream_upload_to_path", new_callable=AsyncMock) as stream,
            patch.object(avatar, "_optimize_avatar", return_value=None),
        ):
            url = await avatar.save_avatar(_upload("image/png"), entry_id)

        assert url == f"/media/directory_avatars/{entry_id}.png"
        stream.assert_awaited_once()
        kwargs = stream.await_args.kwargs
        assert kwargs["max_size"] == avatar.MAX_AVATAR_SIZE
        assert kwargs["allowed_mimes"] == avatar.ALLOWED_AVATAR_TYPES

    async def test_unknown_content_type_falls_back_to_png(self, tmp_path: Path):
        entry_id = uuid.uuid4()
        with (
            patch.object(avatar, "DIRECTORY_AVATARS_DIR", tmp_path),
            patch.object(avatar, "stream_upload_to_path", new_callable=AsyncMock),
            patch.object(avatar, "_optimize_avatar", return_value=None),
        ):
            url = await avatar.save_avatar(_upload("application/octet-stream"), entry_id)

        assert url.endswith(".png")

    async def test_optimized_webp_url(self, tmp_path: Path):
        entry_id = uuid.uuid4()
        with (
            patch.object(avatar, "DIRECTORY_AVATARS_DIR", tmp_path),
            patch.object(avatar, "stream_upload_to_path", new_callable=AsyncMock),
            patch.object(avatar, "_optimize_avatar", return_value="webp"),
        ):
            url = await avatar.save_avatar(_upload("image/jpeg"), entry_id)

        assert url == f"/media/directory_avatars/{entry_id}.webp"


class TestRemoveAvatarFiles:
    def test_removes_existing_files(self, tmp_path: Path):
        entry_id = uuid.uuid4()
        existing = tmp_path / f"{entry_id}.png"
        existing.write_bytes(b"x")
        with patch.object(avatar, "DIRECTORY_AVATARS_DIR", tmp_path):
            avatar.remove_avatar_files(entry_id)
        assert not existing.exists()

    def test_no_error_when_missing(self, tmp_path: Path):
        with patch.object(avatar, "DIRECTORY_AVATARS_DIR", tmp_path):
            avatar.remove_avatar_files(uuid.uuid4())
