"""Unit-тесты app/api/users/avatar_service.py — загрузка/удаление аватара.

Реальная конвертация через Pillow (маленькие PNG) во временном каталоге,
БД-слой замокан. Проверяют: WebP ≤512px, версионированное имя файла,
очистку старых/легаси файлов, сброс фокала, отказ на мусорные байты.
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("PIL", reason="Pillow not installed locally")

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers


def _png_bytes(width: int = 1200, height: int = 900) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(30, 144, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.avatar_url = None
    u.avatar_focal_x = 80
    u.avatar_focal_y = 20
    u.avatar_focal_zoom = 250
    return u


def _make_upload(data: bytes, content_type: str = "image/png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename="avatar.png",
        headers=Headers({"content-type": content_type}),
    )


def _make_db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def avatars_dir(tmp_path, monkeypatch):
    from app.api.users import avatar_service

    monkeypatch.setattr(avatar_service, "AVATARS_DIR", tmp_path)
    yield tmp_path


class TestSaveAvatar:
    async def test_converts_to_webp_and_resizes(self, avatars_dir):
        from app.api.users import avatar_service

        user = _make_user()
        db = _make_db()

        with patch.object(avatar_service.users_repo, "update_user_fields", AsyncMock()) as upd:
            result = await avatar_service.save_avatar(db, user, _make_upload(_png_bytes()))

        assert result is user
        files = list(avatars_dir.iterdir())
        assert len(files) == 1, "tmp и старые файлы должны быть удалены"
        f = files[0]
        assert f.name.startswith(f"{user.id}_") and f.name.endswith(".webp")

        from PIL import Image

        with Image.open(f) as img:
            assert img.format == "WEBP"
            assert max(img.size) <= avatar_service.AVATAR_MAX_DIM

        update_kwargs = upd.call_args.args[2]
        assert update_kwargs["avatar_url"] == f"/media/avatars/{f.name}"
        assert update_kwargs["avatar_focal_x"] is None
        assert update_kwargs["avatar_focal_y"] is None
        assert update_kwargs["avatar_focal_zoom"] is None

    async def test_removes_legacy_and_stale_files(self, avatars_dir):
        from app.api.users import avatar_service

        user = _make_user()
        legacy = avatars_dir / f"{user.id}.jpg"
        legacy.write_bytes(b"legacy")
        stale = avatars_dir / f"{user.id}_1234567.webp"
        stale.write_bytes(b"stale")

        db = _make_db()
        with patch.object(avatar_service.users_repo, "update_user_fields", AsyncMock()):
            await avatar_service.save_avatar(db, user, _make_upload(_png_bytes(64, 64)))

        remaining = [p.name for p in avatars_dir.iterdir()]
        assert len(remaining) == 1
        assert legacy.name not in remaining and stale.name not in remaining

    async def test_rejects_unsupported_content_type(self, avatars_dir):
        from app.api.users import avatar_service

        user = _make_user()
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            await avatar_service.save_avatar(db, user, _make_upload(b"x", "text/plain"))
        assert exc.value.status_code == 422
        assert not list(avatars_dir.iterdir())

    async def test_rejects_garbage_image_bytes(self, avatars_dir):
        from app.api.users import avatar_service

        user = _make_user()
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            await avatar_service.save_avatar(db, user, _make_upload(b"not-an-image"))
        assert exc.value.status_code in (415, 422)
        assert not list(avatars_dir.iterdir())


class TestRemoveAvatar:
    async def test_removes_files_and_clears_db(self, avatars_dir):
        from app.api.users import avatar_service

        user = _make_user()
        (avatars_dir / f"{user.id}.png").write_bytes(b"old")
        (avatars_dir / f"{user.id}_42.webp").write_bytes(b"current")

        db = _make_db()
        with patch.object(avatar_service.users_repo, "update_user_fields", AsyncMock()) as upd:
            result = await avatar_service.remove_avatar(db, user)

        assert result is user
        assert not list(avatars_dir.iterdir())
        update_kwargs = upd.call_args.args[2]
        assert update_kwargs["avatar_url"] is None
        assert update_kwargs["avatar_focal_x"] is None
        assert update_kwargs["avatar_focal_zoom"] is None

    async def test_no_files_is_ok(self, avatars_dir):
        from app.api.users import avatar_service

        user = _make_user()
        db = _make_db()
        with patch.object(avatar_service.users_repo, "update_user_fields", AsyncMock()):
            result = await avatar_service.remove_avatar(db, user)
        assert result is user
